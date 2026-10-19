using System.Buffers.Binary;
using System.Drawing;
using System.Drawing.Imaging;
using System.IO.Pipes;
using System.Net;
using System.Net.Http;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using BlurFing.ScannerComparison;

var tests = new List<(string Name, Func<Task> Run)>();
void Check(string name, Action action) => tests.Add((name, () => { action(); return Task.CompletedTask; }));
void Assert(bool condition, string detail) { if (!condition) throw new Exception(detail); }
void Reject(Action action)
{
    try { action(); }
    catch (Exception error) when (error is InvalidDataException or ArgumentException or JsonException or FormatException) { return; }
    throw new Exception("Invalid contract accepted");
}
var source = ScannerInput.SyntheticPattern();
JsonObject Reply(bool measured = true, bool changed = true)
{
    using var bitmap = source.Preview();
    if (changed) bitmap.SetPixel(0, 0, Color.FromArgb(57, 57, 57));
    using var output = new MemoryStream(); bitmap.Save(output, ImageFormat.Png); var png = output.ToArray();
    return new JsonObject
    {
        ["schema_version"] = "scanner-comparison-v1", ["request_id"] = "synthetic-check",
        ["source_sha256"] = source.Sha, ["source_pixel_sha256"] = source.PixelSha,
        ["processed_image_base64"] = Convert.ToBase64String(png), ["processed_sha256"] = ScannerInput.Hash(png),
        ["width"] = source.Width, ["height"] = source.Height, ["changed_pixels"] = changed ? 1 : 0,
        ["protection_status"] = changed ? "success" : "rejected", ["protection_engine"] = "blurfing-scanner-experimental",
        ["processing_ms"] = 123,
        ["match"] = new JsonObject { ["status"] = measured ? "measured" : "unavailable", ["score"] = measured ? 201.75 : null,
            ["engine"] = "SourceAFIS", ["engine_version"] = measured ? "synthetic-contract-fixture" : null, ["dpi"] = 500,
            ["probe_minutiae"] = measured ? 8 : null, ["candidate_minutiae"] = measured ? 7 : null,
            ["measured_at"] = measured ? "2026-10-20T00:00:00Z" : null }
    };
}
ScannerResult Parse(JsonObject value) => ScannerResult.Parse(Encoding.UTF8.GetBytes(value.ToJsonString()), source, "synthetic-check", 500);

Check("synthetic input is explicit and grayscale PNG pixels survive canonicalization", () =>
{
    var again = ScannerInput.Decode(source.Png, "roundtrip", true);
    Assert(source.Synthetic && again.Width == 300 && again.Height == 400 && again.Gray.SequenceEqual(source.Gray), "pixel/source drift");
    Assert(source.Sha == ScannerInput.Hash(source.Png), "SHA drift");
});
Check("oversized PNG dimensions are rejected before decoding", () =>
{
    var bytes = source.Png.ToArray(); BinaryPrimitives.WriteUInt32BigEndian(bytes.AsSpan(16, 4), 100_000);
    Reject(() => ScannerInput.Decode(bytes, "invalid"));
});
Check("color images cannot be silently treated as scanner data", () =>
{
    using var image = new Bitmap(10, 10); using var graphics = Graphics.FromImage(image); graphics.Clear(Color.Red);
    using var data = new MemoryStream(); image.Save(data, ImageFormat.Png);
    Reject(() => ScannerInput.Decode(data.ToArray(), "color"));
});
Check("measured score remains raw and is never capped at 100 percent", () =>
{
    var result = Parse(Reply()); Assert(result.Score == 201.75 && result.ScoreText == "201.75", "score converted/capped");
});
Check("missing matcher stays unmeasured and rejected output stays explicit", () =>
{
    var result = Parse(Reply(false, false)); Assert(result.Score is null && result.ScoreText == "미측정" && result.ProtectionStatus == "rejected", "false measurement");
});
foreach (var field in new[] { "request_id", "source_sha256", "source_pixel_sha256", "processed_sha256", "protection_engine" })
    Check("wrong identity rejected: " + field, () => { var reply = Reply(); reply[field] = "obsolete"; Reject(() => Parse(reply)); });
Check("changed count or rejected-with-changes is rejected", () =>
{
    var reply = Reply(); reply["changed_pixels"] = 0; Reject(() => Parse(reply));
    reply = Reply(); reply["protection_status"] = "rejected"; Reject(() => Parse(reply));
});
Check("unmeasured score, empty features and negative score cannot become a measurement", () =>
{
    var reply = Reply(false); reply["match"]!["score"] = 1; Reject(() => Parse(reply));
    reply = Reply(); reply["match"]!["probe_minutiae"] = 0; Reject(() => Parse(reply));
    reply = Reply(); reply["match"]!["score"] = -1; Reject(() => Parse(reply));
});
Check("duplicate JSON fields are rejected", () =>
{
    var raw = Reply().ToJsonString().Replace("\"request_id\":\"synthetic-check\"", "\"request_id\":\"synthetic-check\",\"request_id\":\"synthetic-check\"");
    Reject(() => ScannerResult.Parse(Encoding.UTF8.GetBytes(raw), source, "synthetic-check", 500));
});
Check("server URL preserves prefix and rejects nonlocal cleartext or embedded credentials", () =>
{
    Assert(ScannerClient.Normalize("https://example.org/scanner").AbsoluteUri == "https://example.org/scanner/", "prefix");
    Assert(ScannerClient.Normalize("http://127.0.0.1:8002").IsLoopback, "local development");
    foreach (var address in new[] { "http://example.org", "https://user:secret@example.org", "https://example.org?x=1" })
        Reject(() => ScannerClient.Normalize(address));
});
tests.Add(("actual client binds multipart PNG, DPI and request identity", async () =>
{
    var inputBytes = source.Png.ToArray(); var calls = 0;
    using var http = new HttpClient(new Handler(async (request, token) =>
    {
        calls++; Assert(request.RequestUri!.AbsolutePath == "/scanner/v1/scanner/compare", "route");
        var fields = (MultipartFormDataContent)request.Content!;
        var parts = fields.ToDictionary(x => x.Headers.ContentDisposition!.Name!.Trim('"'));
        Assert(parts.Count == 3 && (await parts["image"].ReadAsByteArrayAsync(token)).SequenceEqual(inputBytes), "upload mismatch");
        Assert(await parts["dpi"].ReadAsStringAsync(token) == "500", "DPI");
        return new HttpResponseMessage(HttpStatusCode.OK) { Content = new StringContent(Reply().ToJsonString(), Encoding.UTF8, "application/json") };
    }));
    using var client = new ScannerClient("https://example.org/scanner/", http);
    var result = await client.CompareAsync(source, "synthetic-check", 500, CancellationToken.None);
    Assert(result.ChangedPixels == 1 && calls == 1 && source.Png.SequenceEqual(inputBytes), "request/source changed");
}));
tests.Add(("cancelling a request reaches the HTTP operation", async () =>
{
    var entered = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
    using var http = new HttpClient(new Handler(async (_, token) => { entered.SetResult(); await Task.Delay(30_000, token); return new HttpResponseMessage(); }));
    using var client = new ScannerClient("https://example.org", http); using var cancel = new CancellationTokenSource();
    var work = client.CompareAsync(source, "synthetic-check", 500, cancel.Token); await entered.Task; cancel.Cancel();
    try { await work; throw new Exception("cancel ignored"); } catch (OperationCanceledException) { }
}));
tests.Add(("oversized HTTP response is rejected before parsing", async () =>
{
    using var content = new ByteArrayContent(new byte[40]);
    try { await ScannerClient.ReadLimited(content, 20, CancellationToken.None); throw new Exception("size ignored"); }
    catch (InvalidDataException) { }
}));
tests.Add(("real named pipe ignores a bad sender and receives the next exact PNG", async () =>
{
    using var stop = new CancellationTokenSource(TimeSpan.FromSeconds(10));
    var received = new TaskCompletionSource<byte[]>(TaskCreationOptions.RunContinuationsAsynchronously);
    var listener = FfvReceiver.ListenAsync(bytes => { received.SetResult(bytes); stop.Cancel(); return Task.CompletedTask; }, stop.Token);
    async Task Send(bool bad)
    {
        using var pipe = new NamedPipeClientStream(".", FfvReceiver.PipeName, PipeDirection.Out, PipeOptions.Asynchronous);
        await pipe.ConnectAsync(stop.Token); var header = new byte[9]; Encoding.ASCII.GetBytes(bad ? "WRONG" : "BFSC1").CopyTo(header, 0);
        BinaryPrimitives.WriteInt32LittleEndian(header.AsSpan(5), source.Png.Length);
        await pipe.WriteAsync(header, stop.Token); if (!bad) await pipe.WriteAsync(source.Png, stop.Token);
    }
    await Send(true); await Task.Delay(100); await Send(false);
    Assert((await received.Task.WaitAsync(TimeSpan.FromSeconds(5))).SequenceEqual(source.Png), "pipe data changed"); await listener;
}));
Check("export retains both PNG bytes, raw score metadata and three panels", () =>
{
    var result = Parse(Reply()); var scratch = Path.Combine(Path.GetTempPath(), "BlurFingScannerChecks", Guid.NewGuid().ToString("N"));
    try
    {
        var folder = ComparisonExport.Save(scratch, source, result);
        Assert(File.ReadAllBytes(Path.Combine(folder, "original.png")).SequenceEqual(source.Png), "original changed");
        Assert(File.ReadAllBytes(Path.Combine(folder, "processed.png")).SequenceEqual(result.Png), "processed changed");
        using var image = new Bitmap(Path.Combine(folder, "hstack.png")); Assert(image.Width == 900 && image.Height == 530, "hstack layout");
        using var receipt = JsonDocument.Parse(File.ReadAllText(Path.Combine(folder, "comparison.json")));
        Assert(receipt.RootElement.GetProperty("similarity_score").GetDouble() == 201.75 && receipt.RootElement.GetProperty("input_synthetic").GetBoolean(), "false measurement metadata");
    }
    finally { if (Directory.Exists(scratch)) Directory.Delete(scratch, true); }
});

if (args.Length == 2 && args[0] == "--live-url")
{
    tests.Add(("controlled local HTTP server runs PNG upload, child and response validation", async () =>
    {
        using var client = new ScannerClient(args[1]);
        await client.CheckAsync(CancellationToken.None);
        var result = await client.CompareAsync(source, "synthetic-check", 500, CancellationToken.None);
        Assert(result.ChangedPixels == 1 && result.EngineVersion == "synthetic-contract-fixture", "not the controlled test runtime");
    }));
    tests.Add(("real HTTP cancellation reaches the running child", async () =>
    {
        using var client = new ScannerClient(args[1]); using var cancellation = new CancellationTokenSource(TimeSpan.FromSeconds(2));
        try { await client.CompareAsync(source, "synthetic-cancel", 501, cancellation.Token); throw new Exception("HTTP cancel ignored"); }
        catch (OperationCanceledException) { }
    }));
}
var failures = 0;
foreach (var test in tests)
{
    try { await test.Run(); Console.WriteLine("PASS " + test.Name); }
    catch (Exception error) { failures++; Console.WriteLine("FAIL " + test.Name + " : " + error.Message); }
}
Console.WriteLine($"{tests.Count - failures}/{tests.Count} passed. Synthetic contract fixtures only; no sensor/AI efficacy claim.");
return failures == 0 ? 0 : 1;

sealed class Handler(Func<HttpRequestMessage, CancellationToken, Task<HttpResponseMessage>> send) : HttpMessageHandler
{
    protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken) => send(request, cancellationToken);
}
