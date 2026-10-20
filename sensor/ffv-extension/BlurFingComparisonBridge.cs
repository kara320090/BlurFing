using System;
using System.Drawing;
using System.Drawing.Imaging;
using System.IO;
using System.IO.Pipes;
using System.Threading;
using System.Threading.Tasks;
using System.Windows.Forms;

// Adds live handoff to the official FFV sample without changing SDK acquisition.
internal sealed class BlurFingComparisonBridge : IDisposable
{
    private readonly System.Windows.Forms.Timer timer = new System.Windows.Forms.Timer();
    private readonly ToolStripButton send = new ToolStripButton("Send to comparison");
    private readonly ToolStripLabel state = new ToolStripLabel("Comparison: off");
    private readonly PictureBox preview;
    private Image previous;
    private int busy;
    private bool disposed;

    public BlurFingComparisonBridge(PictureBox picture, ToolStrip toolbar)
    {
        preview = picture;
        send.CheckOnClick = true;
        toolbar.Items.Add(new ToolStripSeparator()); toolbar.Items.Add(send); toolbar.Items.Add(state);
        send.CheckedChanged += delegate { previous = preview.Image; state.Text = send.Checked ? "Comparison: next capture" : "Comparison: off"; };
        timer.Interval = 250;
        timer.Tick += delegate { Tick(); };
        timer.Start();
    }
    private void Tick()
    {
        if (disposed || !send.Checked || preview.Image == null || Object.ReferenceEquals(previous, preview.Image) || Interlocked.CompareExchange(ref busy, 1, 0) != 0) return;
        previous = preview.Image;
        byte[] png;
        try
        {
            using (Bitmap copy = new Bitmap(preview.Image))
            using (MemoryStream data = new MemoryStream())
            {
                copy.Save(data, ImageFormat.Png); png = data.ToArray();
            }
        }
        catch { Interlocked.Exchange(ref busy, 0); state.Text = "Comparison: image unavailable"; return; }
        state.Text = "Comparison: sending";
        Task.Factory.StartNew(delegate
        {
            bool ok = false;
            try
            {
                if (png.Length > 4 * 1024 * 1024) throw new InvalidDataException();
                using (NamedPipeClientStream pipe = new NamedPipeClientStream(".", "BlurFing.ScannerComparison.v1", PipeDirection.Out))
                {
                    pipe.Connect(1500);
                    using (BinaryWriter writer = new BinaryWriter(pipe))
                    {
                        writer.Write(new byte[] {66,70,83,67,49}); writer.Write(png.Length); writer.Write(png); writer.Flush();
                    }
                }
                ok = true;
            }
            catch { }
            finally
            {
                Interlocked.Exchange(ref busy, 0);
                try { if (!disposed && !preview.IsDisposed) preview.BeginInvoke((Action)delegate { if (!disposed) state.Text = ok ? "Comparison: delivered" : "Comparison: open comparison app"; }); }
                catch (InvalidOperationException) { }
            }
        });
    }
    public void Dispose() { disposed = true; timer.Stop(); timer.Dispose(); }
}
