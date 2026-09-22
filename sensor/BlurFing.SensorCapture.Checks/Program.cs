using System.Diagnostics;
using System.Security.Cryptography;
using System.Text.Json;
using BlurFing.SensorCapture;

if (args.Length > 0 && args[0] == "--worker") return CaptureWorker.Run(args);
if (args.Length == 2 && args[0] == "--wait")
{
    File.WriteAllText(args[1], Environment.ProcessId.ToString());
    Thread.Sleep(30000);
    return 0;
}
if (args.Length == 1 && args[0] == "--exit-seven") return 7;

var scratch = Path.Combine(Path.GetTempPath(), "BlurFingChecks", Guid.NewGuid().ToString("N"));
Directory.CreateDirectory(scratch);
var cases = new List<(string Name, Func<Task> Run)>();
void Check(string name, Action action) => cases.Add((name, () => { action(); return Task.CompletedTask; }));
void Assert(bool value, string message) { if (!value) throw new Exception(message); }
void Reject<T>(Action action) where T : Exception
{
    try { action(); } catch (T) { return; }
    throw new Exception($"Expected {typeof(T).Name}");
}
async Task RejectAsync<T>(Func<Task> action) where T : Exception
{
    try { await action(); } catch (T) { return; }
    throw new Exception($"Expected {typeof(T).Name}");
}
var synthetic = CaptureFrame.Synthetic();
Check("synthetic is explicitly labelled, 300x400, 8-bit BMP", () =>
{
    Assert(synthetic.Source == CaptureSource.Synthetic && synthetic.DeviceIndex is null, "source label");
    Assert(synthetic.Width == 300 && synthetic.Height == 400, "dimensions");
    Assert(BitConverter.ToInt16(synthetic.Bmp, 28) == 8, "BMP bit depth");
});
Check("invalid and truncated images are rejected", () =>
{
    Reject<InvalidDataException>(() => CaptureFrame.FromBmp([], CaptureSource.Synthetic));
    Reject<InvalidDataException>(() => CaptureFrame.FromBmp(new byte[54], CaptureSource.Synthetic));
    var truncated = synthetic.Bmp[..54];
    Reject<ArgumentException>(() => CaptureFrame.FromBmp(truncated, CaptureSource.Synthetic));
});
Check("sensor frame requires device identity; synthetic cannot claim a device", () =>
{
    Reject<ArgumentException>(() => CaptureFrame.FromBmp(synthetic.Bmp, CaptureSource.Sensor));
    Reject<ArgumentException>(() => CaptureFrame.FromBmp(synthetic.Bmp, CaptureSource.Sensor, -1));
    Reject<ArgumentException>(() => CaptureFrame.FromBmp(synthetic.Bmp, CaptureSource.Synthetic, 0));
});
Check("capture copies input bytes", () =>
{
    var bytes = (byte[])synthetic.Bmp.Clone();
    var frame = CaptureFrame.FromBmp(bytes, CaptureSource.Synthetic);
    bytes[0] = 0;
    Assert(frame.Bmp[0] == 'B', "input buffer ownership");
});
Check("export preserves BMP, PNG pixels and truthful metadata", () =>
{
    var folder = CaptureExport.Save(synthetic, scratch, "sample01");
    Assert(Path.GetFileName(folder).StartsWith("SYNTHETIC_"), "synthetic filename");
    Assert(File.ReadAllBytes(Path.Combine(folder, "capture.bmp")).SequenceEqual(synthetic.Bmp), "original BMP changed");
    using var original = synthetic.CreatePreview();
    using var png = new Bitmap(Path.Combine(folder, "capture.png"));
    Assert(png.Width == original.Width && png.Height == original.Height, "PNG size");
    for (var y = 0; y < png.Height; y++)
        for (var x = 0; x < png.Width; x++)
            Assert(png.GetPixel(x, y) == original.GetPixel(x, y), "PNG pixel changed");
    using var json = JsonDocument.Parse(File.ReadAllText(Path.Combine(folder, "metadata.json")));
    var root = json.RootElement;
    Assert(root.GetProperty("is_synthetic").GetBoolean(), "synthetic flag");
    Assert(root.GetProperty("source_kind").GetString() == "synthetic_test_pattern", "source kind");
    Assert(root.GetProperty("configured_sensor_model").ValueKind == JsonValueKind.Null, "fake model");
    Assert(root.GetProperty("device_index").ValueKind == JsonValueKind.Null, "fake device");
    Assert(root.GetProperty("bmp_sha256").GetString() == Convert.ToHexString(SHA256.HashData(synthetic.Bmp)).ToLowerInvariant(), "hash");
    Assert(!root.TryGetProperty("match_score", out _) && !root.TryGetProperty("quality_score", out _), "invented scores");
});
Check("repeated saves do not overwrite", () =>
{
    var first = CaptureExport.Save(synthetic, scratch, "repeat");
    var second = CaptureExport.Save(synthetic, scratch, "repeat");
    Assert(first != second && Directory.Exists(first) && Directory.Exists(second), "overwrite");
});
Check("invalid or identifying freeform IDs cannot escape export folder", () =>
{
    var before = Directory.GetDirectories(scratch).Length;
    foreach (var id in new[] { "", "../escape", "C:\\escape", "a/b", "a b", "한글이름", new string('x', 33), "a\n" })
        Reject<ArgumentException>(() => CaptureExport.Save(synthetic, scratch, id));
    Assert(Directory.GetDirectories(scratch).Length == before, "invalid export created files");
});
Check("inaccessible destination fails without claiming success", () =>
{
    var rootFile = Path.Combine(scratch, "not-a-directory");
    File.WriteAllText(rootFile, "test");
    Reject<IOException>(() => CaptureExport.Save(synthetic, rootFile, "sample01"));
});
Check("missing native SDK fails explicitly", () =>
    Reject<FileNotFoundException>(() => new NativeBioMini(Path.Combine(scratch, "missing.dll"))));
Check("wrong DLL missing UFS exports is rejected", () =>
    Reject<EntryPointNotFoundException>(() => new NativeBioMini(Path.Combine(Environment.SystemDirectory, "kernel32.dll"))));
cases.Add(("worker rejects missing SDK without falling back to synthetic", async () =>
    await RejectAsync<FileNotFoundException>(() => WorkerClient.RunAsync("capture", Path.Combine(scratch, "UFScanner.dll"), 0, TimeSpan.FromSeconds(2), CancellationToken.None))));
cases.Add(("worker validates operation, index and DLL name", async () =>
{
    await RejectAsync<ArgumentException>(() => WorkerClient.RunAsync("other", "unused", 0, TimeSpan.FromSeconds(2), CancellationToken.None));
    await RejectAsync<ArgumentOutOfRangeException>(() => WorkerClient.RunAsync("probe", "unused", -1, TimeSpan.FromSeconds(2), CancellationToken.None));
    await RejectAsync<ArgumentException>(() => WorkerClient.RunAsync("probe", Path.Combine(Environment.SystemDirectory, "kernel32.dll"), 0, TimeSpan.FromSeconds(2), CancellationToken.None));
}));
cases.Add(("native worker error reaches client and removes temporary job", async () =>
{
    var sdk = Path.Combine(scratch, "UFScanner.dll");
    // Deliberately invalid bytes exercise the loader error without pretending to supply an SDK.
    File.WriteAllBytes(sdk, [0, 1, 2, 3]);
    var jobs = Path.Combine(Path.GetTempPath(), "BlurFing");
    var before = Directory.Exists(jobs) ? Directory.GetDirectories(jobs).ToHashSet() : [];
    try
    {
        await WorkerClient.RunAsync("capture", sdk, 0, TimeSpan.FromSeconds(10), CancellationToken.None);
        throw new Exception("Invalid DLL unexpectedly produced a capture");
    }
    catch (InvalidOperationException ex) { Assert(ex.Message.Contains("올바른 Windows DLL"), $"specific worker error was lost: {ex.Message}"); }
    Assert(Directory.GetDirectories(jobs).All(before.Contains), "temporary capture job leaked");
}));

ProcessStartInfo Child(params string[] arguments)
{
    var start = new ProcessStartInfo(Environment.ProcessPath!) { UseShellExecute = false, CreateNoWindow = true, WorkingDirectory = scratch };
    foreach (var argument in arguments) start.ArgumentList.Add(argument);
    return start;
}
void AssertChildStopped(string pidFile)
{
    Assert(File.Exists(pidFile), "child did not start before timeout");
    var pid = int.Parse(File.ReadAllText(pidFile));
    try { using var process = Process.GetProcessById(pid); Assert(process.HasExited, "child still running"); }
    catch (ArgumentException) { /* Already removed from the process table. */ }
}
cases.Add(("process exit code is retained", async () =>
    Assert(await ProcessBoundary.RunAsync(Child("--exit-seven"), TimeSpan.FromSeconds(5), CancellationToken.None) == 7, "exit code")));
cases.Add(("timeout terminates the blocked worker", async () =>
{
    var pidFile = Path.Combine(scratch, "timeout.pid");
    await RejectAsync<TimeoutException>(() => ProcessBoundary.RunAsync(Child("--wait", pidFile), TimeSpan.FromSeconds(2), CancellationToken.None));
    AssertChildStopped(pidFile);
}));
cases.Add(("cancel terminates the blocked worker", async () =>
{
    var pidFile = Path.Combine(scratch, "cancel.pid");
    using var cancel = new CancellationTokenSource(TimeSpan.FromSeconds(2));
    await RejectAsync<OperationCanceledException>(() => ProcessBoundary.RunAsync(Child("--wait", pidFile), TimeSpan.FromSeconds(10), cancel.Token));
    AssertChildStopped(pidFile);
}));

var failed = 0;
try
{
    foreach (var test in cases)
    {
        try { await test.Run(); Console.WriteLine($"PASS {test.Name}"); }
        catch (Exception ex) { failed++; Console.WriteLine($"FAIL {test.Name}: {ex}"); }
    }
    Console.WriteLine($"RESULT: {cases.Count - failed}/{cases.Count} passed; hardware/SDK acquisition NOT tested.");
}
finally { Directory.Delete(scratch, recursive: true); }
return failed == 0 ? 0 : 1;
