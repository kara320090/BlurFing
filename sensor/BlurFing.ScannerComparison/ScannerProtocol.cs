using System.Buffers.Binary;
using System.Drawing.Imaging;
using System.Globalization;
using System.Security.Cryptography;
using System.Text.Json;

namespace BlurFing.ScannerComparison;

internal sealed record ScannerInput(byte[] Png, byte[] Gray, int Width, int Height, string Origin, bool Synthetic)
{
    public const int MaxBytes = 4 * 1024 * 1024;
    public string Sha => Hash(Png);
    public string PixelSha => Hash(Gray);
    public static string Hash(byte[] bytes) => Convert.ToHexString(SHA256.HashData(bytes)).ToLowerInvariant();

    public Bitmap Preview()
    {
        using var stream = new MemoryStream(Png);
        using var image = Image.FromStream(stream);
        return new Bitmap(image);
    }

    public static ScannerInput Decode(byte[] bytes, string origin, bool synthetic = false)
    {
        if (bytes.Length < 32 || bytes.Length > MaxBytes) throw new InvalidDataException("영상 파일은 4MiB 이하여야 합니다.");
        long width, height;
        if (bytes.AsSpan(0, 8).SequenceEqual(new byte[] {137,80,78,71,13,10,26,10}))
        {
            width = BinaryPrimitives.ReadUInt32BigEndian(bytes.AsSpan(16, 4));
            height = BinaryPrimitives.ReadUInt32BigEndian(bytes.AsSpan(20, 4));
        }
        else if (bytes[0] == 'B' && bytes[1] == 'M' && bytes.Length >= 54 && BinaryPrimitives.ReadInt32LittleEndian(bytes.AsSpan(14, 4)) >= 40)
        {
            width = BinaryPrimitives.ReadInt32LittleEndian(bytes.AsSpan(18, 4));
            height = Math.Abs((long)BinaryPrimitives.ReadInt32LittleEndian(bytes.AsSpan(22, 4)));
        }
        else throw new InvalidDataException("센서에서 저장한 PNG 또는 BMP를 선택해 주세요.");
        if (width < 1 || height < 1 || width * height > 4_000_000) throw new InvalidDataException("영상은 400만 화소 이하여야 합니다.");
        using var stream = new MemoryStream(bytes);
        using var image = Image.FromStream(stream, false, true);
        if (image.Width != width || image.Height != height || image.GetFrameCount(FrameDimension.Page) > 1)
            throw new InvalidDataException("단일 센서 영상만 사용할 수 있습니다.");
        using var bitmap = new Bitmap(image);
        using var canonical = new Bitmap((int)width, (int)height, PixelFormat.Format8bppIndexed);
        var palette = canonical.Palette;
        for (var i = 0; i < 256; i++) palette.Entries[i] = Color.FromArgb(i, i, i);
        canonical.Palette = palette;
        var gray = new byte[width * height];
        var pixels = canonical.LockBits(new Rectangle(0, 0, canonical.Width, canonical.Height), ImageLockMode.WriteOnly, canonical.PixelFormat);
        try
        {
            var row = new byte[Math.Abs(pixels.Stride)];
            for (var y = 0; y < height; y++)
            {
                for (var x = 0; x < width; x++)
                {
                    var pixel = bitmap.GetPixel(x, y);
                    if (pixel.A != 255 || pixel.R != pixel.G || pixel.G != pixel.B)
                        throw new InvalidDataException("컬러 사진이 아닌 불투명 회색조 센서 영상이 필요합니다.");
                    gray[y * (int)width + x] = row[x] = pixel.R;
                }
                System.Runtime.InteropServices.Marshal.Copy(row, 0, pixels.Scan0 + y * pixels.Stride, row.Length);
            }
        }
        finally { canonical.UnlockBits(pixels); }
        using var output = new MemoryStream();
        canonical.Save(output, ImageFormat.Png);
        if (output.Length > MaxBytes) throw new InvalidDataException("정규화한 PNG가 4MiB를 초과합니다.");
        return new(output.ToArray(), gray, (int)width, (int)height, origin, synthetic);
    }

    public static ScannerInput SyntheticPattern()
    {
        using var image = new Bitmap(300, 400);
        for (var y = 0; y < image.Height; y++)
            for (var x = 0; x < image.Width; x++)
            {
                var value = y < 220 ? x * 255 / 299 : ((x / 25 + y / 25) % 2 == 0 ? 45 : 215);
                image.SetPixel(x, y, Color.FromArgb(value, value, value));
            }
        using var output = new MemoryStream();
        image.Save(output, ImageFormat.Png);
        return Decode(output.ToArray(), "합성 패턴 · 실제 지문 아님", true);
    }
}

internal sealed record ScannerResult(byte[] Png, string RequestId, string ProtectionStatus, int ChangedPixels,
    string MatchStatus, double? Score, string? EngineVersion, int Dpi, int? ProbeMinutiae, int? CandidateMinutiae,
    DateTimeOffset? MeasuredAt, long ProcessingMs)
{
    public string ScoreText => Score is { } score ? score.ToString("0.###", CultureInfo.InvariantCulture) : "미측정";
    public string StatusText => ProtectionStatus == "rejected" ? "처리 거절 · 원본 반환" : "실험 처리본 · 보호 효과 미승인";

    public static ScannerResult Parse(byte[] json, ScannerInput source, string requestId, int dpi)
    {
        using var doc = JsonDocument.Parse(json, new JsonDocumentOptions { MaxDepth = 16 });
        NoDuplicates(doc.RootElement);
        var root = doc.RootElement;
        string Text(string key) => root.GetProperty(key).GetString() ?? throw new InvalidDataException("응답 필드가 없습니다.");
        if (Text("schema_version") != "scanner-comparison-v1" || Text("request_id") != requestId ||
            Text("source_sha256") != source.Sha || Text("source_pixel_sha256") != source.PixelSha ||
            Text("protection_engine") != "blurfing-scanner-experimental") throw new InvalidDataException("현재 원본·요청과 다른 결과입니다.");
        var encoded = Text("processed_image_base64");
        if (encoded.Length > (ScannerInput.MaxBytes + 2) / 3 * 4) throw new InvalidDataException("반환 영상이 너무 큽니다.");
        var png = Convert.FromBase64String(encoded);
        if (Text("processed_sha256") != ScannerInput.Hash(png)) throw new InvalidDataException("반환 PNG 해시가 일치하지 않습니다.");
        var returned = ScannerInput.Decode(png, "서버 처리본");
        if (returned.Width != source.Width || returned.Height != source.Height ||
            root.GetProperty("width").GetInt32() != source.Width || root.GetProperty("height").GetInt32() != source.Height)
            throw new InvalidDataException("반환 영상의 크기가 다릅니다.");
        var changed = source.Gray.Zip(returned.Gray).Count(pair => pair.First != pair.Second);
        var status = Text("protection_status");
        if (root.GetProperty("changed_pixels").GetInt32() != changed ||
            status is not ("success" or "partial_success" or "rejected") || (status == "rejected") != (changed == 0))
            throw new InvalidDataException("처리 상태와 실제 변경 픽셀이 일치하지 않습니다.");
        var match = root.GetProperty("match");
        var matchStatus = match.GetProperty("status").GetString()!;
        if (match.GetProperty("engine").GetString() != "SourceAFIS" || match.GetProperty("dpi").GetInt32() != dpi ||
            matchStatus is not ("measured" or "unmeasurable" or "unavailable")) throw new InvalidDataException("매칭 엔진·조건을 확인하지 못했습니다.");
        double? score = match.GetProperty("score").ValueKind == JsonValueKind.Null ? null : match.GetProperty("score").GetDouble();
        var version = match.GetProperty("engine_version").GetString();
        int? Count(string key) => match.GetProperty(key).ValueKind == JsonValueKind.Null ? null : match.GetProperty(key).GetInt32();
        var probe = Count("probe_minutiae"); var candidate = Count("candidate_minutiae");
        DateTimeOffset? measured = match.GetProperty("measured_at").ValueKind == JsonValueKind.Null ? null : match.GetProperty("measured_at").GetDateTimeOffset();
        if (probe < 0 || candidate < 0 || (matchStatus == "measured" && (score is null || !double.IsFinite(score.Value) || score < 0 ||
            string.IsNullOrWhiteSpace(version) || version.Length > 40 || probe is null or <= 0 || candidate is null or <= 0 || measured is null)) ||
            (matchStatus != "measured" && (score is not null || measured is not null))) throw new InvalidDataException("검증되지 않은 매칭 점수입니다.");
        var elapsed = root.GetProperty("processing_ms").GetInt64();
        if (elapsed < 0) throw new InvalidDataException("처리 시간이 잘못됐습니다.");
        return new(png, requestId, status, changed, matchStatus, score, version, dpi, probe, candidate, measured, elapsed);
    }

    private static void NoDuplicates(JsonElement element)
    {
        if (element.ValueKind == JsonValueKind.Object)
        {
            var names = new HashSet<string>(StringComparer.Ordinal);
            foreach (var item in element.EnumerateObject())
            {
                if (!names.Add(item.Name)) throw new InvalidDataException("중복 응답 필드입니다.");
                NoDuplicates(item.Value);
            }
        }
        else if (element.ValueKind == JsonValueKind.Array) foreach (var item in element.EnumerateArray()) NoDuplicates(item);
    }
}
