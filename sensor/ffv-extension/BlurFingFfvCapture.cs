// Copyright (C) 2026 Lee Bongheon / BlurFing.
// Portions Copyright (C) 2008-2026 Neurotechnology. All Rights Reserved.
// Local extension of the official FFV C# sample, through its public classes.
using System;
using System.Drawing;
using System.Drawing.Imaging;
using System.IO;
using System.Windows.Forms;
using CSharpSample;
using Neurotec.Biometrics;

internal static class BlurFingFfvCapture
{
    private static void Stage(string text)
    {
        string folder = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "BlurFing", "FFVCapture");
        Directory.CreateDirectory(folder);
        File.AppendAllText(Path.Combine(folder, "startup.log"), DateTime.Now.ToString("o") + " " + text + Environment.NewLine);
    }
    [STAThread]
    private static void Main(string[] args)
    {
        if (args.Length == 3 && args[0] == "--transport-self-check" && args[1] == "--capture-once") { BlurFingOneShot.CheckTransport(args[2]); return; }
        if (args.Length == 2 && args[0] == "--capture-once") { BlurFingOneShot.Run(args[1]); return; }
        Stage("Starting");
        Application.EnableVisualStyles();
        Application.SetCompatibleTextRenderingDefault(false);
        Stage("Windows Forms initialized");
        Nffv engine = null;
        try
        {
            Directory.SetCurrentDirectory(AppDomain.CurrentDomain.BaseDirectory);
            // Keep personal data outside source repositories and SDK folders.
            string dataDirectory = Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                "BlurFing", "FFVCapture");
            Directory.CreateDirectory(dataDirectory);
            Stage("Creating scanner selection form");
            using (ChooseScannerForm choose = new ChooseScannerForm())
            {
                Stage("Scanner modules enumerated");
                choose.FingerprintDatabase = Path.Combine(dataDirectory, "fingerprints.dat");
                choose.UserDatabase = Path.Combine(dataDirectory, "users.dat");
                choose.Text = "BlurFing - FFV scanner selection";
                choose.ShowInTaskbar = true;
                choose.StartPosition = FormStartPosition.CenterScreen;
                Stage("Showing scanner selection form");
                if (choose.ShowDialog() != DialogResult.OK) return;
                engine = new Nffv(choose.FingerprintDatabase,
                    choose.FingerprintDatabasePassword, choose.ScannerString);
                using (MainForm form = new MainForm(engine, choose.UserDatabase))
                {
                    form.Text = "BlurFing - FFV image capture (Neurotechnology sample extension)";
                    form.Width = 980;
                    Control[] toolbars = form.Controls.Find("toolStrip1", true);
                    Control[] images = form.Controls.Find("pbExtractedImage", true);
                    if (toolbars.Length != 1 || images.Length != 1)
                        throw new InvalidOperationException("The official sample layout has changed.");
                    PictureBox preview = (PictureBox)images[0];
                    ToolStrip toolbar = (ToolStrip)toolbars[0];
                    ToolStripButton save = new ToolStripButton("Save BMP / PNG");
                    save.Enabled = false;
                    save.Click += delegate { SaveImage(form, preview.Image, dataDirectory); };
                    toolbar.Items.Add(new ToolStripSeparator());
                    toolbar.Items.Add(save);
                    using (BlurFingComparisonBridge bridge = new BlurFingComparisonBridge(preview, toolbar))
                    using (Timer timer = new Timer())
                    {
                        timer.Interval = 300;
                        timer.Tick += delegate { save.Enabled = preview.Image != null; };
                        timer.Start();
                        Application.Run(form);
                    }
                }
            }
        }
        catch (Exception error)
        {
            Stage("Startup error: " + error.Message);
            MessageBox.Show(error.Message + "\r\n\r\nCheck the sensor connection, driver, and SDK files.",
                "BlurFing FFV", MessageBoxButtons.OK, MessageBoxIcon.Error);
        }
        finally
        {
            if (engine != null) engine.Dispose();
        }
    }

    private static void SaveImage(IWin32Window owner, Image image, string directory)
    {
        if (image == null) return;
        using (SaveFileDialog dialog = new SaveFileDialog())
        {
            dialog.Title = "Save the SDK-provided fingerprint image";
            dialog.Filter = "PNG image (*.png)|*.png|Bitmap image (*.bmp)|*.bmp";
            dialog.DefaultExt = "png";
            dialog.AddExtension = true;
            dialog.OverwritePrompt = true;
            dialog.InitialDirectory = directory;
            dialog.FileName = "fingerprint-" + DateTime.Now.ToString("yyyyMMdd-HHmmss");
            if (dialog.ShowDialog(owner) != DialogResult.OK) return;
            string extension = Path.GetExtension(dialog.FileName).ToLowerInvariant();
            if (extension != ".png" && extension != ".bmp")
            {
                MessageBox.Show(owner, "Use a .png or .bmp filename.");
                return;
            }
            try
            {
                // Save the SDK bitmap directly; do not resize or screenshot the preview.
                image.Save(dialog.FileName, extension == ".png" ? ImageFormat.Png : ImageFormat.Bmp);
                MessageBox.Show(owner, "Saved: " + dialog.FileName, "BlurFing FFV");
            }
            catch (Exception error)
            {
                MessageBox.Show(owner, "Save failed: " + error.Message, "BlurFing FFV",
                    MessageBoxButtons.OK, MessageBoxIcon.Error);
            }
        }
    }
}
