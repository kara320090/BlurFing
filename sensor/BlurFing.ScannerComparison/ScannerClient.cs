using System.Globalization;
using System.Net.Http;
using System.Net.Http.Headers;
using System.Text.Json;

namespace BlurFing.ScannerComparison;

internal sealed class ScannerClient : IDisposable
{
    private readonly HttpClient http;
    private readonly Uri root;
    public ScannerClient(string address, HttpClient? client = null)
    {
        root = Normalize(address);
        http = client ?? new HttpClient(new SocketsHttpHandler { AllowAutoRedirect = false, ConnectTimeout = TimeSpan.FromSeconds(30) })
            { Timeout = TimeSpan.FromSeconds(660) };
    }

    internal static Uri Normalize(string address)
    {
        if (!Uri.TryCreate(address.Trim(), UriKind.Absolute, out var uri) || !string.IsNullOrEmpty(uri.UserInfo) ||
            !string.IsNullOrEmpty(uri.Query) || !string.IsNullOrEmpty(uri.Fragment) ||
            !(uri.Scheme == "https" || (uri.Scheme == "http" && uri.IsLoopback)))
            throw new ArgumentException("서버는 HTTPS 주소를 입력하세요. 로컬 시험은 http://127.0.0.1:8002를 사용할 수 있습니다.");
        return new Uri(uri.AbsoluteUri.TrimEnd('/') + "/");
    }

    public async Task CheckAsync(CancellationToken cancellation)
    {
        using var response = await http.GetAsync(new Uri(root, "ready"), HttpCompletionOption.ResponseHeadersRead, cancellation);
        if (!response.IsSuccessStatusCode) throw new InvalidOperationException(ErrorMessage((int)response.StatusCode));
        using var json = JsonDocument.Parse(await ReadLimited(response.Content, 8192, cancellation));
        if (json.RootElement.GetProperty("schema_version").GetString() != "scanner-comparison-v1" ||
            !json.RootElement.GetProperty("configured").GetBoolean()) throw new InvalidDataException("센서 비교용 서버가 아닙니다.");
    }

    public async Task<ScannerResult> CompareAsync(ScannerInput input, string requestId, int dpi, CancellationToken cancellation)
    {
        using var body = new MultipartFormDataContent();
        var image = new ByteArrayContent(input.Png);
        image.Headers.ContentType = new MediaTypeHeaderValue("image/png");
        body.Add(image, "image", "scanner.png"); body.Add(new StringContent(requestId), "request_id");
        body.Add(new StringContent(dpi.ToString(CultureInfo.InvariantCulture)), "dpi");
        using var request = new HttpRequestMessage(HttpMethod.Post, new Uri(root, "v1/scanner/compare")) { Content = body };
        using var response = await http.SendAsync(request, HttpCompletionOption.ResponseHeadersRead, cancellation);
        if (!response.IsSuccessStatusCode) throw new InvalidOperationException(ErrorMessage((int)response.StatusCode));
        return ScannerResult.Parse(await ReadLimited(response.Content, 8 * 1024 * 1024, cancellation), input, requestId, dpi);
    }

    internal static string ErrorMessage(int status) => status switch
    {
        409 => "중복 요청입니다. 새 취득으로 다시 시도해 주세요.",
        413 => "센서 영상의 허용 크기를 초과했습니다.",
        429 => "서버가 다른 영상을 처리 중입니다. 잠시 후 다시 시도해 주세요.",
        503 => "서버의 센서 처리기·실행 환경이 준비되지 않았습니다.",
        504 => "서버 처리 시간이 초과됐습니다. 원본은 유지됩니다.",
        404 => "센서 비교 API가 없습니다. PHOTO/Mock 서버와 다른 센서 전용 주소를 확인해 주세요.",
        _ => $"서버 요청을 완료하지 못했습니다 (HTTP {status}). 원본은 유지됩니다."
    };

    internal static async Task<byte[]> ReadLimited(HttpContent content, int maximum, CancellationToken cancellation)
    {
        if (content.Headers.ContentLength is { } length && (length <= 0 || length > maximum)) throw new InvalidDataException("서버 응답 크기가 잘못됐습니다.");
        await using var input = await content.ReadAsStreamAsync(cancellation);
        using var output = new MemoryStream(); var buffer = new byte[8192];
        while (true)
        {
            var count = await input.ReadAsync(buffer, cancellation);
            if (count == 0) break;
            if (output.Length + count > maximum) throw new InvalidDataException("서버 응답 한도를 초과했습니다.");
            output.Write(buffer, 0, count);
        }
        if (output.Length == 0) throw new InvalidDataException("서버 응답이 비어 있습니다.");
        return output.ToArray();
    }
    public void Dispose() => http.Dispose();
}
