// Windows raw/match bridge, contract blurfing-raw-match-v1.
// NBIS algorithms unchanged. See official NBIS sources for NIST notices.
// Sources of declarations/policy: NBIS 5.0.0 lfs.h, bozorth.h,
// bozorth3/src/bin/bozorth3/bozorth3.c and frozen native/nbis_local.cpp.
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
#include <limits.h>
#include <stdint.h>
#include <memory>

#include <windows.h>
#include <io.h>
#include <fcntl.h>
#include <vector>
#include <string>

static FILE *open_utf8(const char *name, const char *mode) {
    int n = MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS, name, -1, NULL, 0);
    if (!n) { errno = EINVAL; return NULL; }
    std::vector<wchar_t> wide(n);
    if (!MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS, name, -1, wide.data(), n))
        return NULL;
    std::wstring wmode;
    for (const char *p = mode; *p; ++p) wmode.push_back(static_cast<wchar_t>(*p));
    return _wfopen(wide.data(), wmode.c_str());
}
#define fopen open_utf8


extern "C" {
#include <lfs.h>
#include <bozorth.h>

// CLI-owned globals: exact types from the official CLI and bozorth.h.
// Core algorithm arrays are already defined in libbozorth3 (bz_gbls.c).
int m1_xyt = 0; // NIST internal XYT, not M1.
int max_minutiae = 150;
int min_computable_minutiae = 10;
int verbose_main = 0;
int verbose_load = 0;
int verbose_bozorth = 0;
int verbose_threshold = 0;
FILE *errorfp = NULL; // Set to stderr before any library call.
}

struct FreeMemory {
    template<typename T> void operator()(T *p) const { free(p); }
};
struct CloseFile {
    void operator()(FILE *p) const { if (p) fclose(p); }
};
typedef std::unique_ptr<FILE, CloseFile> File;
typedef std::unique_ptr<xyt_struct, FreeMemory> Template;

struct Extraction {
    MINUTIAE *minutiae;
    int *quality, *direction, *low_contrast, *low_flow, *high_curve;
    unsigned char *binary;
    Extraction() : minutiae(NULL), quality(NULL), direction(NULL),
        low_contrast(NULL), low_flow(NULL), high_curve(NULL), binary(NULL) {}
    ~Extraction() {
        if (minutiae) free_minutiae(minutiae);
        free(quality); free(direction); free(low_contrast);
        free(low_flow); free(high_curve); free(binary);
    }
    Extraction(const Extraction &) = delete;
    Extraction &operator=(const Extraction &) = delete;
};

static int fail(int code, const char *message) {
    fprintf(stderr, "%s\n", message);
    return code;
}

// Unlike the frozen atoi parser, reject whitespace, suffixes and overflow.
static bool positive_integer(const char *text, int &value) {
    if (!text || !*text) return false;
    const char *digits = (*text == '+' || *text == '-') ? text + 1 : text;
    if (!*digits) return false;
    for (const char *p = digits; *p; ++p)
        if (*p < '0' || *p > '9') return false;
    errno = 0;
    char *end = NULL;
    long parsed = strtol(text, &end, 10);
    if (errno == ERANGE || *end || parsed <= 0 || parsed > INT_MAX)
        return false;
    value = static_cast<int>(parsed);
    return true;
}

static int raw(const char *path, int width, int height, int dpi,
               const char *output) {
    if (width < 1 || height < 1 || width > 4096 || height > 4096)
        return fail(2, "Dimensions must be 1..4096");
    if (static_cast<size_t>(width) > SIZE_MAX / static_cast<size_t>(height))
        return fail(2, "Raw dimensions overflow");
    const size_t size = static_cast<size_t>(width) * static_cast<size_t>(height);
    File input(fopen(path, "rb"));
    if (!input) return fail(3, "Cannot open raw input");
    std::unique_ptr<unsigned char, FreeMemory> data(
        static_cast<unsigned char *>(malloc(size)));
    if (!data) return fail(4, "Raw allocation failed");
    if (fread(data.get(), 1, size, input.get()) != size)
        return fail(3, "Raw input is short or unreadable");
    // Exact size required: frozen bridge accepted trailing bytes.
    if (fgetc(input.get()) != EOF || ferror(input.get()))
        return fail(3, "Raw size must equal width * height");
    if (fclose(input.release()) != 0)
        return fail(3, "Raw input close failed");

    Extraction result;
    int map_width = 0, map_height = 0, binary_width = 0;
    int binary_height = 0, binary_depth = 0;
    int code = get_minutiae(&result.minutiae, &result.quality,
        &result.direction, &result.low_contrast, &result.low_flow,
        &result.high_curve, &map_width, &map_height, &result.binary,
        &binary_width, &binary_height, &binary_depth, data.get(),
        width, height, 8, dpi / 25.4, &lfsparms_V2);
    if (code) {
        fprintf(stderr, "get_minutiae=%d\n", code);
        return 2;
    }
    if (!result.minutiae || result.minutiae->num < 0 ||
        (result.minutiae->num > 0 && !result.minutiae->list))
        return fail(2, "Invalid extraction result");
    for (int i = 0; i < result.minutiae->num; ++i)
        if (!result.minutiae->list[i])
            return fail(2, "Null extracted minutia");

    // Full extraction count retained; no pruning or 150-row limit here.
    lfs2nist_format(result.minutiae, width, height);
    File file(fopen(output, "wb"));
    if (!file) return fail(3, "Cannot open XYT output");
    for (int i = 0; i < result.minutiae->num; ++i) {
        MINUTIA *p = result.minutiae->list[i];
        // lfs2nist_format already converts reliability to percent quality.
        if (fprintf(file.get(), "%d %d %d %d\n", p->x, p->y,
                    p->direction, static_cast<int>(p->reliability)) < 0)
            return fail(3, "XYT write failed");
    }
    if (fclose(file.release()) != 0) return fail(3, "XYT close failed");
    if (printf("%d\n", result.minutiae->num) < 0 || fflush(stdout) != 0)
        return fail(3, "Count output failed");
    return 0;
}

static Template load(const char *path) {
    File file(fopen(path, "r"));
    if (!file) { fail(3, "Cannot open XYT input"); return Template(); }
    xytq_struct q;
    memset(&q, 0, sizeof(q));
    int x, y, theta, quality;
    // Deliberately preserve frozen fscanf semantics: whitespace-separated
    // groups of four integers, not strict lines. Malformed/incomplete trailing
    // input stops parsing and retains complete preceding groups. Do not add
    // range correction, row filtering or a stricter trailing-input policy.
    while (fscanf(file.get(), "%d %d %d %d", &x, &y, &theta, &quality) == 4) {
        if (q.nrows >= MAX_FILE_MINUTIAE) {
            fail(3, "XYT exceeds 1000 complete entries"); return Template();
        }
        int i = q.nrows++;
        q.xcol[i] = x; q.ycol[i] = y;
        q.thetacol[i] = theta; q.qualitycol[i] = quality;
    }
    // Real I/O errors are failures, unlike a normal scanf matching failure.
    if (ferror(file.get())) { fail(3, "XYT read failed"); return Template(); }
    if (fclose(file.release()) != 0) {
        fail(3, "XYT input close failed"); return Template();
    }
    Template result(bz_prune(&q, 0));
    if (!result) fail(3, "Template pruning failed");
    return result;
}

static int match(const char *probe_path, const char *gallery_path) {
    Template probe = load(probe_path);
    if (!probe) return 3;
    Template gallery = load(gallery_path);
    if (!gallery) return 3;
    const int score = bozorth_main(probe.get(), gallery.get());
    // Low feature counts remain visible to the Python adapter; do not turn
    // insufficient features into an accepted nonmatch or retry extraction.
    if (printf("%d %d %d\n", score, probe->nrows, gallery->nrows) < 0 ||
        fflush(stdout) != 0) return fail(3, "Match output failed");
    return 0;
}

static int bridge_main(int argc, char **argv) {
    errorfp = stderr;
    if (argc == 4 && strcmp(argv[1], "match") == 0)
        return match(argv[2], argv[3]);
    if (argc == 7 && strcmp(argv[1], "raw") == 0) {
        int width, height, dpi;
        if (!positive_integer(argv[3], width) ||
            !positive_integer(argv[4], height) ||
            !positive_integer(argv[5], dpi))
            return fail(2, "Width, height and DPI must be positive integers");
        return raw(argv[2], width, height, dpi, argv[6]);
    }
    return fail(2, "raw FILE WIDTH HEIGHT DPI OUT | match PROBE GALLERY");
}

// Build with MinGW-w64 g++ -municode; preserve UTF-8 paths and LF stdout.
int wmain(int argc, wchar_t **wide_argv) {
    if (_setmode(_fileno(stdout), _O_BINARY) == -1) return fail(3, "stdout mode failed");
    std::vector<std::string> storage;
    storage.reserve(argc);
    for (int i = 0; i < argc; ++i) {
        int n = WideCharToMultiByte(CP_UTF8, WC_ERR_INVALID_CHARS, wide_argv[i], -1,
                                  NULL, 0, NULL, NULL);
        if (!n) return fail(3, "Invalid UTF-16 argument");
        std::string value(n, '\0');
        if (!WideCharToMultiByte(CP_UTF8, WC_ERR_INVALID_CHARS, wide_argv[i], -1,
                                &value[0], n, NULL, NULL)) return fail(3, "Argument conversion failed");
        storage.push_back(value);
    }
    std::vector<char *> argv;
    for (std::string &value : storage) argv.push_back(&value[0]);
    return bridge_main(argc, argv.data());
}
