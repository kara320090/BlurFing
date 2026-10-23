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

// Child used only by this checks executable: exercises the actual one-shot
// process/pipe lifetime without loading a driver or pretending to scan a finger.
if (args.Length == 3 && args[1] == "--capture-once")
{
    using var fixturePipe = new NamedPipeClientStream(".", args[2], PipeDirection.InOut);
    fixturePipe.Connect(5000);
    if (args[0] == "--fixture-wait") { fixturePipe.ReadByte(); return 0; }
    using var writer = new BinaryWriter(fixturePipe);
    writer.Write(Encoding.ASCII.GetBytes(args[0] == "--fixture-invalid" ? "WRONG" : "BFSC2"));
    var fixtureBytes = args[0] == "--fixture-ok" ? ScannerInput.SyntheticPattern().Png : [];
    writer.Write((byte)(args[0] == "--fixture-cancel" ? 1 : args[0] == "--fixture-cleanup" ? 3
        : args[0] == "--fixture-noscan" ? 4 : args[0] == "--fixture-timeout" ? 5 : args[0] == "--fixture-quality" ? 6 : 0));
    writer.Write(fixtureBytes.Length); writer.Write(fixtureBytes); writer.Flush();
    return 0;
}

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

if (args.Length == 3 && args[0] == "--render-export-preview")
{
    var raw = double.Parse(args[2], System.Globalization.CultureInfo.InvariantCulture);
    var reply = Reply(); reply["match"]!["score"] = raw;
    Console.WriteLine(ComparisonExport.Save(Path.GetFullPath(args[1]), source, Parse(reply)));
    return 0;
}

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
Check("display scale handles reported low and high scores with a fixed reference", () =>
{
    foreach (var example in new[] { (Raw: 0.0, Index: 0.0, Text: "0.0"), (Raw: 0.9, Index: 2.200488997555012, Text: "2.2"),
        (Raw: 40.0, Index: 50.0, Text: "50.0"), (Raw: 298.0, Index: 88.16568047337278, Text: "88.2") })
    {
        var reply = Reply(); reply["match"]!["score"] = example.Raw; var result = Parse(reply);
        Assert(result.Score == example.Raw && Math.Abs(result.Score100!.Value - example.Index) < 1e-10
            && result.Score100Text == example.Text, "raw/index/reference mismatch");
    }
});
Check("display scale stays ordered and bounded without treating invalid values as zero", () =>
{
    double previous = -1;
    foreach (var raw in new[] { 0, .9, 40, 100, 298, 1000, 1e100, double.MaxValue })
    {
        var value = MatchScoreScale.Convert(raw)!.Value;
        Assert(double.IsFinite(value) && value >= previous && value >= 0 && value <= 100, "scale range/order");
        previous = value;
    }
    foreach (var invalid in new double?[] { null, -1, double.NaN, double.PositiveInfinity, double.NegativeInfinity })
        Assert(MatchScoreScale.Convert(invalid) is null && MatchScoreScale.Format(invalid) == "미측정", "false zero measurement");
});
Check("unmeasured results never acquire a display index", () =>
{
    var result = Parse(Reply(false));
    Assert(result.Score100 is null && result.Score100Text == "미측정", "unavailable became a score");
    var reply = Reply(false); reply["match"]!["status"] = "unmeasurable";
    result = Parse(reply);
    Assert(result.Score100 is null && result.Score100Text == "미측정", "unmeasurable became a score");
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
    var pipeName = "BlurFing.Checks." + Guid.NewGuid().ToString("N");
    var received = new TaskCompletionSource<byte[]>(TaskCreationOptions.RunContinuationsAsynchronously);
    var listener = FfvReceiver.ListenAsync(bytes => { received.SetResult(bytes); stop.Cancel(); return Task.CompletedTask; }, stop.Token, pipeName);
    async Task Send(bool bad)
    {
        using var pipe = new NamedPipeClientStream(".", pipeName, PipeDirection.Out, PipeOptions.Asynchronous);
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
        Assert(receipt.RootElement.GetProperty("input_origin").GetString() == source.Origin, "input origin lost");
        Assert(Math.Abs(receipt.RootElement.GetProperty("similarity_index_100").GetDouble() - result.Score100!.Value) < 1e-10,
            "exported display index disagrees with UI");
        Assert(receipt.RootElement.GetProperty("similarity_index_method").GetString() == MatchScoreScale.Method &&
            receipt.RootElement.GetProperty("similarity_index_reference").GetDouble() == 40 &&
            receipt.RootElement.GetProperty("similarity_index_formula").GetString() == MatchScoreScale.Formula &&
            receipt.RootElement.GetProperty("similarity_index_unit").GetString()!.Contains("not_probability"), "display scale provenance lost");
    }
    finally { if (Directory.Exists(scratch)) Directory.Delete(scratch, true); }
});
Check("unavailable matcher export keeps both raw and display score null", () =>
{
    var scratch = Path.Combine(Path.GetTempPath(), "BlurFingScannerChecks", Guid.NewGuid().ToString("N"));
    try
    {
        var folder = ComparisonExport.Save(scratch, source, Parse(Reply(false)));
        using var receipt = JsonDocument.Parse(File.ReadAllText(Path.Combine(folder, "comparison.json")));
        Assert(receipt.RootElement.GetProperty("similarity_score").ValueKind == JsonValueKind.Null &&
            receipt.RootElement.GetProperty("similarity_index_100").ValueKind == JsonValueKind.Null, "export created false zero");
    }
    finally { if (Directory.Exists(scratch)) Directory.Delete(scratch, true); }
});

System.Diagnostics.ProcessStartInfo CaptureFixture(string mode)
{
    var start = new System.Diagnostics.ProcessStartInfo(Path.Combine(AppContext.BaseDirectory, "BlurFing.ScannerComparison.Checks.exe"));
    start.ArgumentList.Add(mode); start.CreateNoWindow = true; return start;
}
Check("comparison executable and legacy FFV executable are rejected as one-shot helpers", () =>
{
    var self = Path.Combine(AppContext.BaseDirectory, "BlurFing.ScannerComparison.exe");
    Assert(FfvHelperConfiguration.Problem(self) is not null, "comparison program accepted as capture helper");
    Assert(FfvHelperConfiguration.Problem(typeof(ScannerInput).Assembly.Location) is not null, "ordinary managed program accepted");
    Assert(FfvHelperConfiguration.Resolve(self, "missing-helper.exe") is null, "invalid saved selection persisted");
});
tests.Add(("comparison executable is refused before spawning another UI or waiting for a pipe", async () =>
{
    try
    {
        await FfvCaptureClient.CaptureAsync(new System.Diagnostics.ProcessStartInfo(
            Path.Combine(AppContext.BaseDirectory, "BlurFing.ScannerComparison.exe")), CancellationToken.None);
    }
    catch (ArgumentException) { return; }
    throw new Exception("recursive comparison launch accepted");
}));

if (args.Length == 2 && args[0] == "--ffv-helper")
{
    Check("installed official SDK helper is recognized and recovers an incorrect saved path", () =>
    {
        var helper = Path.GetFullPath(args[1]);
        Assert(FfvHelperConfiguration.Problem(helper) is null, "installed helper rejected: " + FfvHelperConfiguration.Problem(helper));
        Assert(FfvHelperConfiguration.Resolve("BlurFing.ScannerComparison.exe", helper) == helper, "portable recovery failed");
        Assert(FfvHelperConfiguration.Resolve(helper, "missing-helper.exe") == helper, "valid personal choice overwritten");
        var scratch = Path.Combine(Path.GetTempPath(), "BlurFingScannerChecks", Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(scratch);
        try
        {
            var copy = Path.Combine(scratch, Path.GetFileName(helper)); File.Copy(helper, copy);
            Assert(FfvHelperConfiguration.Problem(copy) is not null, "helper without installed SDK dependencies accepted");
        }
        finally { Directory.Delete(scratch, true); }
    });
    tests.Add(("installed Framework helper sends a frame while its cancellation read is pending", async () =>
    {
        using var stop = new CancellationTokenSource(TimeSpan.FromSeconds(3));
        var start = new System.Diagnostics.ProcessStartInfo(Path.GetFullPath(args[1]));
        start.ArgumentList.Add("--transport-self-check"); start.CreateNoWindow = true;
        try { await FfvCaptureClient.CaptureAsync(start, stop.Token); }
        catch (OperationCanceledException) when (!stop.IsCancellationRequested) { return; }
        throw new Exception("duplex transport did not return its explicit cancellation frame before deadline");
    }));
    tests.Add(("SDK indexed bitmap reserved alpha normalizes without changing grayscale samples", async () =>
    {
        using var stop = new CancellationTokenSource(TimeSpan.FromSeconds(5));
        var start = new System.Diagnostics.ProcessStartInfo(Path.GetFullPath(args[1]));
        start.ArgumentList.Add("--bitmap-self-check"); start.CreateNoWindow = true;
        var actual = await FfvCaptureClient.CaptureAsync(start, stop.Token);
        Assert(actual.Width == 3 && actual.Height == 2 && actual.Gray.SequenceEqual(new byte[] { 12, 34, 56, 78, 90, 123 }), "SDK grayscale samples changed");
    }));
    tests.Add(("unadapted indexed PNG alpha is still rejected by the ordinary input validator", async () =>
    {
        using var stop = new CancellationTokenSource(TimeSpan.FromSeconds(5));
        var start = new System.Diagnostics.ProcessStartInfo(Path.GetFullPath(args[1]));
        start.ArgumentList.Add("--bitmap-raw-self-check"); start.CreateNoWindow = true;
        try { await FfvCaptureClient.CaptureAsync(start, stop.Token); }
        catch (InvalidDataException) { return; }
        throw new Exception("transparent indexed input was accepted without the SDK boundary adapter");
    }));
    tests.Add(("raw device callback filters empty/no-contact frames and preserves exact source pixels", async () =>
    {
        using var stop = new CancellationTokenSource(TimeSpan.FromSeconds(5));
        var start = new System.Diagnostics.ProcessStartInfo(Path.GetFullPath(args[1]));
        start.ArgumentList.Add("--raw-frame-self-check"); start.CreateNoWindow = true;
        var actual = await FfvCaptureClient.CaptureAsync(start, stop.Token);
        Assert(actual.Width == 3 && actual.Height == 2 && actual.Gray.SequenceEqual(new byte[] { 12, 34, 56, 78, 90, 123 }), "raw SDK samples or dimensions changed");
    }));
}
tests.Add(("scanner absence, acquisition timeout and poor quality stay distinct failures", async () =>
{
    foreach (var failure in new[] { (Mode: "--fixture-noscan", Text: "센서를 찾지"),
        (Mode: "--fixture-timeout", Text: "20초"), (Mode: "--fixture-quality", Text: "품질 검사") })
    {
        try { await FfvCaptureClient.CaptureAsync(CaptureFixture(failure.Mode), CancellationToken.None); }
        catch (InvalidOperationException error) when (error.Message.Contains(failure.Text)) { continue; }
        throw new Exception("missing precise acquisition failure: " + failure.Mode);
    }
}));
tests.Add(("one-click capture receives the fresh helper image without disk image transport", async () =>
{
    var captured = await FfvCaptureClient.CaptureAsync(CaptureFixture("--fixture-ok"), CancellationToken.None);
    Assert(captured.Gray.SequenceEqual(source.Gray) && captured.Origin.Contains("새로 취득"), "capture pixels/origin mismatch");
}));
tests.Add(("one-click capture rejects bad framing and cleanup failure without an image", async () =>
{
    foreach (var mode in new[] { "--fixture-invalid", "--fixture-cleanup" })
    {
        try { await FfvCaptureClient.CaptureAsync(CaptureFixture(mode), CancellationToken.None); throw new Exception("invalid capture accepted"); }
        catch (Exception error) when (error is InvalidDataException or InvalidOperationException) { }
    }
}));
tests.Add(("cancelled acquisition cannot become a valid capture", async () =>
{
    try { await FfvCaptureClient.CaptureAsync(CaptureFixture("--fixture-cancel"), CancellationToken.None); throw new Exception("cancel ignored"); }
    catch (OperationCanceledException) { }
    using var stop = new CancellationTokenSource(TimeSpan.FromSeconds(1));
    try { await FfvCaptureClient.CaptureAsync(CaptureFixture("--fixture-wait"), stop.Token); throw new Exception("owner cancel ignored"); }
    catch (OperationCanceledException) { }
    // A subsequent fresh process still works; cancellation didn't poison its channel.
    var next = await FfvCaptureClient.CaptureAsync(CaptureFixture("--fixture-ok"), CancellationToken.None);
    Assert(next.Gray.SequenceEqual(source.Gray), "next request failed");
}));

if (args.Length == 2 && args[0] == "--live-url")
{
    tests.Add(("controlled local HTTP server runs PNG upload, child and response validation", async () =>
    {
        using var client = new ScannerClient(args[1]);
        await client.CheckAsync(CancellationToken.None);
        var result = await client.CompareAsync(source, "synthetic-check", 500, CancellationToken.None);
        Assert(result.ChangedPixels == 1 && result.EngineVersion == "synthetic-contract-fixture", "not the controlled test runtime");
    }));
    tests.Add(("one-click child image reaches local API worker, validated score and export", async () =>
    {
        var captured = await FfvCaptureClient.CaptureAsync(CaptureFixture("--fixture-ok"), CancellationToken.None);
        using var client = new ScannerClient(args[1]);
        var result = await client.CompareAsync(captured, "oneclick-synthetic-check", 500, CancellationToken.None);
        Assert(result.Score == 123.5 && result.EngineVersion == "synthetic-contract-fixture", "fixture worker response mismatch");
        var scratch = Path.Combine(Path.GetTempPath(), "BlurFingScannerChecks", Guid.NewGuid().ToString("N"));
        try
        {
            var folder = ComparisonExport.Save(scratch, captured, result);
            Assert(File.ReadAllBytes(Path.Combine(folder, "original.png")).SequenceEqual(captured.Png), "fresh capture bytes lost");
            Assert(File.Exists(Path.Combine(folder, "hstack.png")), "comparison export missing");
        }
        finally { if (Directory.Exists(scratch)) Directory.Delete(scratch, true); }
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
