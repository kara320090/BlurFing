// Copyright (C) 2026 Lee Bongheon / BlurFing.
// Uses the installed official FFV SDK public API; no SDK binaries are redistributed.
using System;
using System.Drawing;
using System.Drawing.Imaging;
using System.IO;
using System.IO.Pipes;
using System.Runtime.InteropServices;
using System.Text.RegularExpressions;
using System.Threading;
using System.Threading.Tasks;
using System.Windows.Forms;
using CSharpSample;
using Neurotec.Biometrics;

internal static class BlurFingOneShot
{
    private static void Stage(string stage)
    {
        try
        {
            string root = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "BlurFing", "FFVOneShot");
            Directory.CreateDirectory(root);
            string path = Path.Combine(root, "last-attempt.log");
            if (stage == "start") File.WriteAllText(path, "");
            // Fixed stages, SDK status and exception TYPE only; no images, user IDs,
            // templates, database passwords, exception messages or stack traces.
            File.AppendAllText(path, DateTime.Now.ToString("o") + " " + stage + Environment.NewLine);
        }
        catch { }
    }

    internal static NamedPipeClientStream OpenPipe(string pipeName)
    {
        // A blocking cancellation read must not serialize writes on the same
        // synchronous Windows pipe handle. Both directions use overlapped I/O.
        return new NamedPipeClientStream(".", pipeName, PipeDirection.InOut, PipeOptions.Asynchronous);
    }

    internal static void CheckTransport(string pipeName)
    {
        if (!Regex.IsMatch(pipeName, @"\ABlurFing\.Capture\.[0-9a-f]{32}\z")) return;
        using (NamedPipeClientStream pipe = OpenPipe(pipeName))
        {
            pipe.Connect(5000);
            ManualResetEvent reading = new ManualResetEvent(false);
            Task.Factory.StartNew(delegate { reading.Set(); try { pipe.ReadByte(); } catch { } });
            reading.WaitOne(); Thread.Sleep(100);
            // Transport contract check: cancellation frame, no SDK/GUI/biometric data.
            using (BinaryWriter writer = new BinaryWriter(pipe))
            {
                writer.Write(new byte[] { 66, 70, 83, 67, 50, 1, 0, 0, 0, 0 }); writer.Flush();
            }
        }
    }

    internal static byte[] EncodeScannerBitmap(Bitmap image)
    {
        if (image.Width < 1 || image.Height < 1 || (long)image.Width * image.Height > 4000000)
            throw new InvalidDataException("Scanner bitmap dimensions");
        using (Bitmap canonical = new Bitmap(image.Width, image.Height, PixelFormat.Format8bppIndexed))
        {
            ColorPalette palette = canonical.Palette;
            for (int i = 0; i < 256; i++) palette.Entries[i] = Color.FromArgb(255, i, i, i);
            canonical.Palette = palette;
            BitmapData data = canonical.LockBits(new Rectangle(0, 0, image.Width, image.Height), ImageLockMode.WriteOnly, canonical.PixelFormat);
            try
            {
                byte[] row = new byte[Math.Abs(data.Stride)];
                for (int y = 0; y < image.Height; y++)
                {
                    for (int x = 0; x < image.Width; x++)
                    {
                        // SDK GetBitmap is a physical grayscale HBITMAP. Its unused
                        // palette alpha is not input transparency. Copy luminance
                        // exactly; never resize, enhance or convert color to gray.
                        Color pixel = image.GetPixel(x, y);
                        if (pixel.R != pixel.G || pixel.G != pixel.B) throw new InvalidDataException("Scanner bitmap is not grayscale");
                        row[x] = pixel.R;
                    }
                    Marshal.Copy(row, 0, IntPtr.Add(data.Scan0, y * data.Stride), row.Length);
                }
            }
            finally { canonical.UnlockBits(data); }
            using (MemoryStream output = new MemoryStream())
            {
                canonical.Save(output, ImageFormat.Png);
                if (output.Length > 4 * 1024 * 1024) throw new InvalidDataException("Scanner PNG size");
                return output.ToArray();
            }
        }
    }

    internal static void CheckBitmapTransport(string pipeName, bool canonicalize)
    {
        if (!Regex.IsMatch(pipeName, @"\ABlurFing\.Capture\.[0-9a-f]{32}\z")) return;
        using (Bitmap image = new Bitmap(3, 2, PixelFormat.Format8bppIndexed))
        using (NamedPipeClientStream pipe = OpenPipe(pipeName))
        {
            ColorPalette palette = image.Palette;
            for (int i = 0; i < 256; i++) palette.Entries[i] = Color.FromArgb(0, i, i, i);
            image.Palette = palette;
            BitmapData data = image.LockBits(new Rectangle(0, 0, 3, 2), ImageLockMode.WriteOnly, image.PixelFormat);
            try
            {
                Marshal.Copy(new byte[] { 12, 34, 56, 0 }, 0, data.Scan0, 4);
                Marshal.Copy(new byte[] { 78, 90, 123, 0 }, 0, IntPtr.Add(data.Scan0, data.Stride), 4);
            }
            finally { image.UnlockBits(data); }
            byte[] bytes;
            if (canonicalize) bytes = EncodeScannerBitmap(image);
            else { using (MemoryStream stream = new MemoryStream()) { image.Save(stream, ImageFormat.Png); bytes = stream.ToArray(); } }
            pipe.Connect(5000);
            using (BinaryWriter writer = new BinaryWriter(pipe))
            {
                writer.Write(new byte[] { 66, 70, 83, 67, 50, 0 }); writer.Write(bytes.Length); writer.Write(bytes); writer.Flush();
            }
        }
    }

    internal static void Run(string pipeName)
    {
        if (!Regex.IsMatch(pipeName, @"\ABlurFing\.Capture\.[0-9a-f]{32}\z")) return;
        Stage("start");
        using (NamedPipeClientStream pipe = OpenPipe(pipeName))
        {
            try { pipe.Connect(5000); }
            catch { return; }
            Stage("pipe-connected");
            Application.EnableVisualStyles(); Application.SetCompatibleTextRenderingDefault(false);
            Directory.SetCurrentDirectory(AppDomain.CurrentDomain.BaseDirectory);
            string root = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "BlurFing", "FFVOneShot");
            string scratch = Path.Combine(root, Guid.NewGuid().ToString("N"));
            string modulesFile = Path.Combine(root, "scanner-modules.txt");
            Nffv engine = null; Form dialog = null; int cancelled = 0;
            byte status = 2; byte[] png = null; bool cleaned = true;
            // Owner disconnect/cancel never leaves a waiting SDK enrollment behind.
            Task.Factory.StartNew(delegate
            {
                try { pipe.ReadByte(); } catch { }
                Interlocked.Exchange(ref cancelled, 1);
                try { if (engine != null) engine.Cancel(); } catch { }
                try { if (dialog != null && dialog.IsHandleCreated) dialog.BeginInvoke((Action)delegate { dialog.Close(); }); } catch { }
            });
            try
            {
                Directory.CreateDirectory(scratch);
                string modules = null;
                string[] available = Nffv.GetAvailableScannerModules().Split(new[] { ';' }, StringSplitOptions.RemoveEmptyEntries);
                Stage("modules-enumerated");
                if (File.Exists(modulesFile))
                {
                    string saved = File.ReadAllText(modulesFile);
                    string[] requested = saved.Split(new[] { ';' }, StringSplitOptions.RemoveEmptyEntries);
                    if (requested.Length > 0 && Array.TrueForAll(requested, delegate(string m) { return Array.IndexOf(available, m) >= 0; })) modules = saved;
                }
                if (modules == null)
                {
                    using (ChooseScannerForm choose = new ChooseScannerForm())
                    {
                        dialog = choose;
                        choose.Text = "BlurFing | 최초 1회 BioMini 스캐너 모듈 선택";
                        choose.FingerprintDatabase = Path.Combine(scratch, "capture.dat");
                        choose.UserDatabase = Path.Combine(scratch, "unused-users.dat");
                        choose.Shown += delegate { if (Volatile.Read(ref cancelled) != 0) choose.Close(); };
                        if (Volatile.Read(ref cancelled) != 0 || choose.ShowDialog() != DialogResult.OK) { status = 1; return; }
                        modules = choose.ScannerString;
                        // Store scanner module names only, never database credentials or images.
                        File.WriteAllText(modulesFile, modules);
                    }
                }
                using (Form progress = new Form())
                {
                    dialog = progress;
                    progress.Text = "BlurFing | 새 지문 취득";
                    progress.ClientSize = new Size(440, 150); progress.StartPosition = FormStartPosition.CenterScreen;
                    progress.FormBorderStyle = FormBorderStyle.FixedDialog; progress.MaximizeBox = false;
                    Label text = new Label { Dock = DockStyle.Fill, Padding = new Padding(20), Text = "센서에 손가락을 올려 주세요.\r\n새 지문을 취득하면 서버 비교로 이어집니다.", AutoSize = false };
                    Button cancel = new Button { Dock = DockStyle.Bottom, Height = 38, Text = "취득 취소" };
                    progress.Controls.Add(text); progress.Controls.Add(cancel);
                    cancel.Click += delegate { progress.Close(); };
                    bool complete = false;
                    progress.FormClosing += delegate(object sender, FormClosingEventArgs e)
                    {
                        if (!complete) { Interlocked.Exchange(ref cancelled, 1); try { if (engine != null) engine.Cancel(); } catch { } e.Cancel = true; text.Text = "취득을 취소하는 중입니다…"; }
                    };
                    progress.Shown += async delegate
                    {
                        byte failureStatus = 2;
                        try
                        {
                            if (Volatile.Read(ref cancelled) != 0) { status = 1; return; }
                            // Match the official FFV C# sample: initialize the SDK
                            // on its STA UI thread; only Enroll runs on a worker.
                            engine = new Nffv(Path.Combine(scratch, "capture.dat"), Guid.NewGuid().ToString("N"), modules);
                            Stage("engine-opened-" + Thread.CurrentThread.GetApartmentState().ToString());
                            png = await Task.Run(delegate
                            {
                                if (Volatile.Read(ref cancelled) != 0) return (byte[])null;
                                // FFV exposes Enroll/GetBitmap, not raw Capture. Use a new
                                // private database for THIS request, then remove it before send.
                                NffvStatus outcome;
                                NffvUser user = engine.Enroll(20000, out outcome);
                                Stage("enroll-status-" + outcome.ToString());
                                failureStatus = outcome == NffvStatus.NoScanner ? (byte)4
                                    : outcome == NffvStatus.ScannerTimeout ? (byte)5
                                    : outcome == NffvStatus.QualityCheckFailed ? (byte)6 : (byte)2;
                                if (Volatile.Read(ref cancelled) != 0 || outcome != NffvStatus.TemplateCreated || user == null) return (byte[])null;
                                using (Bitmap image = user.GetBitmap())
                                {
                                    Stage("bitmap-" + image.Width + "x" + image.Height + "-" + image.PixelFormat.ToString());
                                    if ((image.PixelFormat & PixelFormat.Indexed) != 0)
                                    {
                                        Color[] entries = image.Palette.Entries;
                                        int alphaMin = 255, alphaMax = 0;
                                        foreach (Color color in entries) { alphaMin = Math.Min(alphaMin, color.A); alphaMax = Math.Max(alphaMax, color.A); }
                                        Stage("bitmap-palette-alpha-" + alphaMin + "-" + alphaMax);
                                    }
                                    return EncodeScannerBitmap(image);
                                }
                            });
                            status = Volatile.Read(ref cancelled) != 0 ? (byte)1 : png != null ? (byte)0 : failureStatus;
                        }
                        catch (Exception error) { Stage("capture-error-" + error.GetType().Name); status = Volatile.Read(ref cancelled) != 0 ? (byte)1 : (byte)2; }
                        finally { complete = true; progress.Close(); }
                    };
                    progress.ShowDialog();
                }
            }
            catch (Exception error) { Stage("setup-error-" + error.GetType().Name); status = Volatile.Read(ref cancelled) != 0 ? (byte)1 : (byte)2; }
            finally
            {
                dialog = null;
                if (engine != null)
                {
                    try { engine.Users.Clear(); } catch { cleaned = false; }
                    try { engine.Dispose(); } catch { cleaned = false; }
                    engine = null;
                }
                // Only a freshly generated directory immediately below FFVOneShot.
                try { if (Directory.Exists(scratch)) Directory.Delete(scratch, true); } catch { cleaned = false; }
                if (!cleaned) { status = 3; png = null; }
                if (Volatile.Read(ref cancelled) != 0 && status != 3) status = 1;
                Stage("cleanup-" + (cleaned ? "ok" : "failed"));
                try
                {
                    using (BinaryWriter writer = new BinaryWriter(pipe))
                    {
                        writer.Write(new byte[] { 66, 70, 83, 67, 50 }); writer.Write(status);
                        writer.Write(status == 0 ? png.Length : 0);
                        if (status == 0) writer.Write(png);
                        writer.Flush();
                        Stage("response-sent-" + status.ToString());
                    }
                }
                catch { }
            }
        }
    }
}
