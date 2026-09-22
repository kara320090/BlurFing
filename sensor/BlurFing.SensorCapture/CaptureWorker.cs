using System.ComponentModel;
using System.Diagnostics;
using System.Text.Json;

namespace BlurFing.SensorCapture;

internal sealed record WorkerReply(bool Success, int DeviceCount, string? Error);
internal sealed record AcquisitionResult(int DeviceCount, CaptureFrame? Frame);

internal static class CaptureWorker
{
    public static int Run(string[] args)
    {
        WorkerReply reply;
        try
        {
            if (args.Length != 4 || (args[1] != "probe" && args[1] != "capture") ||
                !int.TryParse(args[3], out var index) || index < 0)
                throw new ArgumentException("잘못된 작업 요청입니다.");
            using var sensor = new NativeBioMini(args[2]);
            var count = sensor.GetDeviceCount();
            if (args[1] == "capture") sensor.Capture(index);
            reply = new(true, count, null);
        }
        catch (BadImageFormatException)
        {
            reply = new(false, 0, "SDK DLL과 프로그램의 비트 수가 다르거나 올바른 Windows DLL이 아닙니다. x64/x86 버전을 맞추세요.");
        }
        catch (DllNotFoundException)
        {
            reply = new(false, 0, "SDK 또는 종속 DLL을 불러오지 못했습니다. SDK의 재배포 폴더 구조와 필요한 런타임을 확인하세요.");
        }
        catch (EntryPointNotFoundException)
        {
            reply = new(false, 0, "필수 UFS 함수가 없습니다. BioMini Windows SDK의 UFScanner.dll과 버전을 확인하세요.");
        }
        catch (Exception ex)
        {
            reply = new(false, 0, ex.Message);
        }
        File.WriteAllText("result.json", JsonSerializer.Serialize(reply));
        return reply.Success ? 0 : 1;
    }
}

internal static class ProcessBoundary
{
    public static async Task<int> RunAsync(ProcessStartInfo start, TimeSpan timeout, CancellationToken cancellation)
    {
        cancellation.ThrowIfCancellationRequested();
        using var process = Process.Start(start) ?? throw new Win32Exception("취득 프로세스를 시작하지 못했습니다.");
        using var deadline = new CancellationTokenSource(timeout);
        using var linked = CancellationTokenSource.CreateLinkedTokenSource(cancellation, deadline.Token);
        try
        {
            await process.WaitForExitAsync(linked.Token);
            return process.ExitCode;
        }
        catch (OperationCanceledException)
        {
            if (!process.HasExited)
            {
                try { process.Kill(entireProcessTree: true); }
                catch (InvalidOperationException) { /* Exited between the check and Kill. */ }
            }
            await process.WaitForExitAsync(CancellationToken.None);
            if (cancellation.IsCancellationRequested) throw new OperationCanceledException(cancellation);
            throw new TimeoutException("센서 응답 시간이 초과되어 취득 프로세스를 종료했습니다. USB를 확인하고 다시 시도하세요.");
        }
    }
}

internal static class WorkerClient
{
    public static async Task<AcquisitionResult> RunAsync(string operation, string sdkPath, int index,
        TimeSpan timeout, CancellationToken cancellation)
    {
        if (operation != "probe" && operation != "capture") throw new ArgumentException("알 수 없는 작업입니다.");
        if (index < 0) throw new ArgumentOutOfRangeException(nameof(index));
        sdkPath = Path.GetFullPath(sdkPath);
        if (!File.Exists(sdkPath)) throw new FileNotFoundException("UFScanner.dll을 먼저 선택하세요.");
        if (!string.Equals(Path.GetFileName(sdkPath), "UFScanner.dll", StringComparison.OrdinalIgnoreCase))
            throw new ArgumentException("BioMini SDK의 UFScanner.dll을 선택하세요.");

        var job = Path.Combine(Path.GetTempPath(), "BlurFing", Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(job);
        try
        {
            var executable = Environment.ProcessPath ?? throw new InvalidOperationException("실행 파일 경로가 없습니다.");
            var start = new ProcessStartInfo(executable) { UseShellExecute = false, CreateNoWindow = true, WorkingDirectory = job };
            if (Path.GetFileNameWithoutExtension(executable).Equals("dotnet", StringComparison.OrdinalIgnoreCase))
                start.ArgumentList.Add(Path.Combine(AppContext.BaseDirectory, "BlurFing.SensorCapture.dll"));
            foreach (var argument in new[] { "--worker", operation, sdkPath, index.ToString(System.Globalization.CultureInfo.InvariantCulture) })
                start.ArgumentList.Add(argument);
            var exit = await ProcessBoundary.RunAsync(start, timeout, cancellation);
            cancellation.ThrowIfCancellationRequested();
            var responsePath = Path.Combine(job, "result.json");
            if (!File.Exists(responsePath))
                throw new InvalidOperationException($"SDK 취득 프로세스가 종료되었습니다 (코드 {exit}). SDK 버전·드라이버·장치를 확인하세요.");
            var reply = JsonSerializer.Deserialize<WorkerReply>(await File.ReadAllTextAsync(responsePath, cancellation))
                ?? throw new InvalidDataException("SDK 결과를 읽지 못했습니다.");
            if (!reply.Success || exit != 0) throw new InvalidOperationException(reply.Error ?? "센서 작업 실패");
            if (operation == "probe") return new(reply.DeviceCount, null);
            var bmp = Path.Combine(job, "capture.bmp");
            if (!File.Exists(bmp)) throw new InvalidDataException("SDK가 BMP 파일을 생성하지 않았습니다.");
            if (new FileInfo(bmp).Length > 20_000_000) throw new InvalidDataException("취득 이미지 크기가 제한을 초과했습니다.");
            var frame = CaptureFrame.FromBmp(await File.ReadAllBytesAsync(bmp, cancellation), CaptureSource.Sensor, index);
            return new(reply.DeviceCount, frame);
        }
        finally
        {
            // Only this invocation's random directory is removed, after the worker exits.
            Directory.Delete(job, recursive: true);
        }
    }
}
