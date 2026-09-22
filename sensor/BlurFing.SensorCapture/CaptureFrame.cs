using System.Drawing.Imaging;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text.Json;
using System.Text.RegularExpressions;

namespace BlurFing.SensorCapture;

internal enum CaptureSource { Sensor, Synthetic }

internal sealed class CaptureFrame
{
    public byte[] Bmp { get; }
    public CaptureSource Source { get; }
    public int? DeviceIndex { get; }
    public int Width { get; }
    public int Height { get; }
    public DateTimeOffset AcquiredUtc { get; }

    private CaptureFrame(byte[] bmp, CaptureSource source, int? deviceIndex, int width, int height)
    {
        Bmp = bmp; Source = source; DeviceIndex = deviceIndex; Width = width; Height = height;
        AcquiredUtc = DateTimeOffset.UtcNow;
    }

    public static CaptureFrame FromBmp(byte[] bmp, CaptureSource source, int? deviceIndex = null)
    {
        if (bmp.Length < 54 || bmp.Length > 20_000_000 || bmp[0] != 'B' || bmp[1] != 'M')
            throw new InvalidDataException("올바른 BMP 영상이 아닙니다.");
        using var stream = new MemoryStream(bmp);
        using var image = Image.FromStream(stream, useEmbeddedColorManagement: false, validateImageData: true);
        if (image.Width < 1 || image.Height < 1 || (long)image.Width * image.Height > 4_000_000)
            throw new InvalidDataException("영상 해상도가 제한을 초과했습니다.");
        if (source == CaptureSource.Sensor && (deviceIndex is null || deviceIndex < 0))
            throw new ArgumentException("센서 영상에는 장치 인덱스가 필요합니다.");
        if (source == CaptureSource.Synthetic && deviceIndex is not null)
            throw new ArgumentException("합성 영상에 센서 인덱스를 기록할 수 없습니다.");
        return new((byte[])bmp.Clone(), source, deviceIndex, image.Width, image.Height);
    }

    public Bitmap CreatePreview()
    {
        using var stream = new MemoryStream(Bmp);
        using var image = Image.FromStream(stream);
        return new Bitmap(image);
    }

    public static CaptureFrame Synthetic()
    {
        // Checkerboard and gradient only. This deliberately does not resemble a fingerprint.
        using var bitmap = new Bitmap(300, 400, PixelFormat.Format8bppIndexed);
        var palette = bitmap.Palette;
        for (var i = 0; i < 256; i++) palette.Entries[i] = Color.FromArgb(i, i, i);
        bitmap.Palette = palette;
        var data = bitmap.LockBits(new Rectangle(0, 0, bitmap.Width, bitmap.Height), ImageLockMode.WriteOnly, bitmap.PixelFormat);
        try
        {
            var bytes = new byte[data.Stride * bitmap.Height];
            for (var y = 0; y < bitmap.Height; y++)
                for (var x = 0; x < bitmap.Width; x++)
                    bytes[y * data.Stride + x] = (byte)(y < 220 ? x * 255 / 299 : (((x / 25) + (y / 25)) % 2 == 0 ? 45 : 215));
            Marshal.Copy(bytes, 0, data.Scan0, bytes.Length);
        }
        finally { bitmap.UnlockBits(data); }
        using var output = new MemoryStream();
        bitmap.Save(output, ImageFormat.Bmp);
        return FromBmp(output.ToArray(), CaptureSource.Synthetic);
    }
}

internal sealed record CaptureMetadata(
    int SchemaVersion, string SampleId, string SourceKind, bool IsSynthetic,
    string? ConfiguredSensorModel, int? DeviceIndex, DateTimeOffset AcquiredUtc,
    int Width, int Height, string BmpSha256, string BmpFile, string PngFile, string Note);

internal static partial class CaptureExport
{
    [GeneratedRegex("\\A[A-Za-z0-9_-]{1,32}\\z", RegexOptions.CultureInvariant)]
    private static partial Regex SampleIdPattern();

    public static string DefaultRoot => Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "BlurFing", "Captures");

    public static string Save(CaptureFrame frame, string root, string sampleId)
    {
        if (!SampleIdPattern().IsMatch(sampleId))
            throw new ArgumentException("익명 ID는 영문·숫자·밑줄·하이픈 1~32자로 입력하세요. 이름이나 학번은 쓰지 마세요.");
        var prefix = frame.Source == CaptureSource.Synthetic ? "SYNTHETIC" : "SENSOR";
        var directory = Path.Combine(Path.GetFullPath(root), $"{prefix}_{sampleId}_{DateTime.UtcNow:yyyyMMddTHHmmss}_{Guid.NewGuid():N}");
        Directory.CreateDirectory(directory);
        try
        {
            File.WriteAllBytes(Path.Combine(directory, "capture.bmp"), frame.Bmp);
            using var preview = frame.CreatePreview();
            preview.Save(Path.Combine(directory, "capture.png"), ImageFormat.Png);
            var synthetic = frame.Source == CaptureSource.Synthetic;
            var metadata = new CaptureMetadata(1, sampleId, synthetic ? "synthetic_test_pattern" : "biomini_sdk",
                synthetic, synthetic ? null : "BioMini Slim 2 (configured, model not queried)", frame.DeviceIndex,
                frame.AcquiredUtc, frame.Width, frame.Height, Convert.ToHexString(SHA256.HashData(frame.Bmp)).ToLowerInvariant(),
                "capture.bmp", "capture.png", synthetic
                    ? "Synthetic gradient/checkerboard; not a fingerprint or measured protection result."
                    : "Original SDK BMP retained. No quality, identity match, liveness or protection measurement performed.");
            File.WriteAllText(Path.Combine(directory, "metadata.json"), JsonSerializer.Serialize(metadata,
                new JsonSerializerOptions { WriteIndented = true, PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower }));
            return directory;
        }
        catch
        {
            Directory.Delete(directory, recursive: true);
            throw;
        }
    }
}
