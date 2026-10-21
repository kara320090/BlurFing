// Copyright (C) 2026 Lee Bongheon / BlurFing.
// Device grayscale callback; no FFV enrollment, template or liveness setting changes.
using System;
using System.Diagnostics;
using System.Drawing;
using System.Drawing.Imaging;
using System.IO;
using System.IO.Pipes;
using System.Runtime.InteropServices;
using System.Text.RegularExpressions;
using System.Threading;
using System.Threading.Tasks;
using System.Windows.Forms;

internal sealed class RawFrame
{
    internal readonly int Width, Height, Ppi;
    internal readonly byte[] Pixels;
    internal RawFrame(int width, int height, int ppi, byte[] pixels)
    {
        if (width < 1 || height < 1 || (long)width * height > 4000000 || pixels == null || pixels.Length != (long)width * height || ppi != 500)
            throw new InvalidDataException("Invalid device frame dimensions or resolution");
        Width = width; Height = height; Ppi = ppi; Pixels = pixels;
    }
    internal byte[] Png()
    {
        using (Bitmap image = new Bitmap(Width, Height, PixelFormat.Format8bppIndexed))
        {
            ColorPalette palette = image.Palette;
            for (int i = 0; i < 256; i++) palette.Entries[i] = Color.FromArgb(255, i, i, i);
            image.Palette = palette; image.SetResolution(Ppi, Ppi);
            BitmapData data = image.LockBits(new Rectangle(0, 0, Width, Height), ImageLockMode.WriteOnly, image.PixelFormat);
            try { for (int y = 0; y < Height; y++) Marshal.Copy(Pixels, y * Width, IntPtr.Add(data.Scan0, y * data.Stride), Width); }
            finally { image.UnlockBits(data); }
            using (MemoryStream output = new MemoryStream()) { image.Save(output, ImageFormat.Png); return output.ToArray(); }
        }
    }
}

internal sealed class RawFrameReceiver
{
    private readonly object sync = new object();
    private int consecutive;
    internal int Frames, FingerFrames;
    internal volatile string Error;
    internal RawFrame Ready;
    internal int Receive(IntPtr scanner, int finger, IntPtr pixels, int width, int height, int ppi, IntPtr parameter)
    {
        try
        {
            lock (sync)
            {
                Frames++;
                if (finger == 0) { consecutive = 0; return 1; }
                FingerFrames++;
                if (pixels == IntPtr.Zero || width < 1 || height < 1 || (long)width * height > 4000000)
                    throw new InvalidDataException("Invalid callback buffer");
                byte[] copy = new byte[checked(width * height)]; Marshal.Copy(pixels, copy, 0, copy.Length);
                RawFrame frame = new RawFrame(width, height, ppi, copy);
                // Ignore uniform empty frames. No biometric quality/liveness claim.
                bool variable = false; foreach (byte value in copy) if (value != copy[0]) { variable = true; break; }
                if (!variable) { consecutive = 0; return 1; }
                if (++consecutive >= 3) Ready = frame;
                return 1;
            }
        }
        catch (Exception error) { Error = error.GetType().Name; return 0; }
    }
    internal RawFrame Snapshot() { lock (sync) return Ready; }
}

internal static class BlurFingRawOneShot
{
    private static void Log(string stage) { BlurFingOneShot.Stage(stage); }
    internal static void CheckFrameTransport(string pipeName)
    {
        if (!Regex.IsMatch(pipeName, @"\ABlurFing\.Capture\.[0-9a-f]{32}\z")) return;
        // Pure callback contract fixture. Does not load or initialize UFScanner.
        RawFrameReceiver receiver = new RawFrameReceiver();
        byte[] pixels = new byte[] { 12, 34, 56, 78, 90, 123 };
        IntPtr memory = Marshal.AllocHGlobal(pixels.Length);
        try
        {
            Marshal.Copy(new byte[6], 0, memory, 6);
            for (int i = 0; i < 3; i++) receiver.Receive(IntPtr.Zero, 1, memory, 3, 2, 500, IntPtr.Zero);
            if (receiver.Snapshot() != null) throw new InvalidDataException("Empty frame accepted");
            Marshal.Copy(pixels, 0, memory, 6);
            for (int i = 0; i < 2; i++) receiver.Receive(IntPtr.Zero, 1, memory, 3, 2, 500, IntPtr.Zero);
            if (receiver.Snapshot() != null) throw new InvalidDataException("Contact accepted too early");
            receiver.Receive(IntPtr.Zero, 0, memory, 3, 2, 500, IntPtr.Zero);
            for (int i = 0; i < 3; i++) receiver.Receive(IntPtr.Zero, 1, memory, 3, 2, 500, IntPtr.Zero);
            RawFrame ready = receiver.Snapshot();
            if (ready == null) throw new InvalidDataException("Contact frame missing");
            using (NamedPipeClientStream pipe = BlurFingOneShot.OpenPipe(pipeName))
            {
                pipe.Connect(5000); byte[] png = ready.Png();
                using (BinaryWriter writer = new BinaryWriter(pipe))
                { writer.Write(new byte[] { 66, 70, 83, 67, 50, 0 }); writer.Write(png.Length); writer.Write(png); writer.Flush(); }
            }
        }
        finally { Marshal.FreeHGlobal(memory); }
    }
    internal static void Run(string pipeName)
    {
        if (!Regex.IsMatch(pipeName, @"\ABlurFing\.Capture\.[0-9a-f]{32}\z")) return;
        Log("start"); Log("backend-UFS-raw-500ppi");
        using (NamedPipeClientStream pipe = BlurFingOneShot.OpenPipe(pipeName))
        {
            try { pipe.Connect(5000); } catch { return; }
            Application.EnableVisualStyles(); Application.SetCompatibleTextRenderingDefault(false);
            int cancelled = 0; Form dialog = null; NativeScanner native = null;
            bool started = false, cleaned = true; byte status = 2; byte[] png = null;
            RawFrameReceiver receiver = new RawFrameReceiver();
            Task.Factory.StartNew(delegate
            {
                try { pipe.ReadByte(); } catch { }
                Interlocked.Exchange(ref cancelled, 1);
                try { if (dialog != null && dialog.IsHandleCreated) dialog.BeginInvoke((Action)delegate { dialog.Close(); }); } catch { }
            });
            try
            {
                string dll = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "FScanners", "NdmSupremaBioMini", "UFScanner.dll");
                using (Form progress = new Form())
                {
                    dialog = progress;
                    progress.Text = "BlurFing | 센서 원본 지문 취득";
                    progress.ClientSize = new Size(460, 160); progress.StartPosition = FormStartPosition.CenterScreen;
                    progress.FormBorderStyle = FormBorderStyle.FixedDialog; progress.MaximizeBox = false;
                    Label text = new Label { Dock = DockStyle.Fill, Padding = new Padding(20), Text = "센서 중앙에 맨손 손가락을 넓게 올려 주세요.\r\n원본을 얻으면 자동으로 서버 비교를 시작합니다." };
                    Button cancel = new Button { Dock = DockStyle.Bottom, Height = 38, Text = "취득 취소" };
                    progress.Controls.Add(text); progress.Controls.Add(cancel); cancel.Click += delegate { progress.Close(); };
                    bool complete = false;
                    progress.FormClosing += delegate(object sender, FormClosingEventArgs e)
                    { if (!complete) { Interlocked.Exchange(ref cancelled, 1); e.Cancel = true; text.Text = "센서 취득을 중단하는 중입니다…"; } };
                    progress.Shown += async delegate
                    {
                        try
                        {
                            if (Volatile.Read(ref cancelled) != 0) { status = 1; return; }
                            native = new NativeScanner(dll, delegate(string name, string detail) { Log(name + " " + detail); });
                            native.Open(); Log("scanner-count-" + native.ScannerCount);
                            if (native.ScannerCount != 1) { status = 4; return; }
                            native.ConfigureTimeout(21000); native.Start(receiver.Receive); started = true;
                            RawFrame frame = await Task.Run(delegate
                            {
                                Stopwatch timer = Stopwatch.StartNew();
                                while (timer.ElapsedMilliseconds < 20000 && Volatile.Read(ref cancelled) == 0)
                                {
                                    if (receiver.Error != null) throw new InvalidDataException("Invalid native frame");
                                    RawFrame ready = receiver.Snapshot(); if (ready != null) return ready;
                                    if (!native.IsCapturing()) break;
                                    Thread.Sleep(40);
                                }
                                return (RawFrame)null;
                            });
                            if (Volatile.Read(ref cancelled) != 0) status = 1;
                            else if (frame == null) status = 5;
                            else { png = frame.Png(); status = 0; Log("raw-frame-" + frame.Width + "x" + frame.Height + "-ppi-" + frame.Ppi); }
                        }
                        catch (Exception error) { Log("capture-error-" + error.GetType().Name); status = Volatile.Read(ref cancelled) != 0 ? (byte)1 : (byte)2; }
                        finally { complete = true; progress.Close(); }
                    };
                    progress.ShowDialog();
                }
            }
            catch (Exception error) { Log("setup-error-" + error.GetType().Name); status = 2; }
            finally
            {
                dialog = null;
                if (native != null)
                {
                    try { if (started) native.Stop(); native.Close(); }
                    catch (Exception error) { cleaned = false; Log("shutdown-error-" + error.GetType().Name); }
                }
                Log("frames-" + receiver.Frames + "-finger-" + receiver.FingerFrames);
                if (!cleaned) { status = 3; png = null; }
                if (Volatile.Read(ref cancelled) != 0 && status != 3) { status = 1; png = null; }
                Log("cleanup-" + (cleaned ? "ok" : "failed"));
                try
                {
                    using (BinaryWriter writer = new BinaryWriter(pipe))
                    {
                        writer.Write(new byte[] { 66, 70, 83, 67, 50 }); writer.Write(status); writer.Write(status == 0 ? png.Length : 0);
                        if (status == 0) writer.Write(png); writer.Flush(); Log("response-sent-" + status);
                    }
                }
                catch { }
                GC.KeepAlive(native); // callback and module stay rooted through native shutdown
            }
        }
    }
}
