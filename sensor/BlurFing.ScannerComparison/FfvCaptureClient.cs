using System.Buffers.Binary;
using System.Diagnostics;
using System.IO.Pipes;

namespace BlurFing.ScannerComparison;

// One fresh helper process and a private, same-user pipe per button click.
// The legacy preview pipe is deliberately not used for a requested capture.
internal static class FfvCaptureClient
{
    internal static async Task<ScannerInput> CaptureAsync(ProcessStartInfo start, CancellationToken cancellation)
    {
        if (FfvHelperConfiguration.IsComparisonProgram(start.FileName))
            throw new ArgumentException("비교 프로그램은 FFV 취득기로 실행할 수 없습니다. FFV 위치 설정에서 원클릭 취득기를 선택하세요.");
        var name = "BlurFing.Capture." + Guid.NewGuid().ToString("N");
        await using var pipe = new NamedPipeServerStream(name, PipeDirection.InOut, 1,
            PipeTransmissionMode.Byte, PipeOptions.Asynchronous | PipeOptions.CurrentUserOnly);
        start.UseShellExecute = false;
        start.WorkingDirectory = Path.GetDirectoryName(Path.GetFullPath(start.FileName))!;
        start.ArgumentList.Add("--capture-once"); start.ArgumentList.Add(name);
        using var process = Process.Start(start) ?? throw new InvalidOperationException("FFV 취득기를 시작하지 못했습니다.");
        using var deadline = CancellationTokenSource.CreateLinkedTokenSource(cancellation);
        deadline.CancelAfter(TimeSpan.FromSeconds(90)); // includes first-time scanner selection
        try
        {
            var connection = pipe.WaitForConnectionAsync(deadline.Token);
            var exit = process.WaitForExitAsync(deadline.Token);
            if (await Task.WhenAny(connection, exit) == exit && !pipe.IsConnected)
            {
                deadline.Token.ThrowIfCancellationRequested();
                throw new InvalidOperationException("FFV 취득기가 종료됐습니다. 전체 SDK 위치와 센서 드라이버를 확인하세요.");
            }
            await connection;
            var header = new byte[10];
            await pipe.ReadExactlyAsync(header, deadline.Token);
            if (!header.AsSpan(0, 5).SequenceEqual("BFSC2"u8)) throw new InvalidDataException("FFV 취득 응답 형식 오류");
            var length = BinaryPrimitives.ReadInt32LittleEndian(header.AsSpan(6));
            if (header[5] != 0)
            {
                if (length != 0 || header[5] > 3) throw new InvalidDataException("FFV 취득 응답 형식 오류");
                if (header[5] == 1) throw new OperationCanceledException("FFV 취득 취소", cancellation);
                throw new InvalidOperationException(header[5] == 3
                    ? "FFV 임시 지문 자료 정리에 실패했습니다. 취득기 안내를 확인하세요. 서버로 전송하지 않았습니다."
                    : "새 지문 취득에 실패했습니다. 센서 연결·손가락 접촉·SDK 드라이버를 확인하세요.");
            }
            if (length < 32 || length > ScannerInput.MaxBytes) throw new InvalidDataException("FFV 영상 크기 오류");
            var png = new byte[length]; await pipe.ReadExactlyAsync(png, deadline.Token);
            deadline.Token.ThrowIfCancellationRequested();
            return ScannerInput.Decode(png, "FFV 버튼으로 새로 취득한 센서 영상");
        }
        finally
        {
            // Closing the pipe requests Nffv.Cancel in the helper, including while
            // selecting a scanner. Never kill another FFV instance or its service.
            pipe.Dispose();
            if (!process.HasExited)
            {
                try { await process.WaitForExitAsync().WaitAsync(TimeSpan.FromSeconds(5)); }
                catch (TimeoutException) { if (!process.HasExited) process.Kill(); }
            }
        }
    }
}
