using System.Buffers.Binary;
using System.IO.Pipes;

namespace BlurFing.ScannerComparison;

internal static class FfvReceiver
{
    public const string PipeName = "BlurFing.ScannerComparison.v1";
    public static async Task ListenAsync(Func<byte[], Task> received, CancellationToken cancellation)
    {
        while (!cancellation.IsCancellationRequested)
        {
            try
            {
                await using var pipe = new NamedPipeServerStream(PipeName, PipeDirection.In, 1,
                    PipeTransmissionMode.Byte, PipeOptions.Asynchronous | PipeOptions.CurrentUserOnly);
                await pipe.WaitForConnectionAsync(cancellation);
                using var deadline = CancellationTokenSource.CreateLinkedTokenSource(cancellation);
                deadline.CancelAfter(TimeSpan.FromSeconds(5));
                var header = new byte[9];
                await pipe.ReadExactlyAsync(header, deadline.Token);
                if (!header.AsSpan(0, 5).SequenceEqual("BFSC1"u8)) continue;
                var length = BinaryPrimitives.ReadInt32LittleEndian(header.AsSpan(5));
                if (length < 32 || length > ScannerInput.MaxBytes) continue;
                var png = new byte[length];
                await pipe.ReadExactlyAsync(png, deadline.Token);
                await received(png);
            }
            catch (Exception error) when (error is IOException or OperationCanceledException or InvalidDataException)
            {
                // A malformed/disconnected sender cannot close the next capture listener.
                if (cancellation.IsCancellationRequested) break;
                try { await Task.Delay(250, cancellation); }
                catch (OperationCanceledException) { break; }
            }
        }
    }
}
