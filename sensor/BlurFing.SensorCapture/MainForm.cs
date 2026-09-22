using System.Diagnostics;
using System.Runtime.InteropServices;

namespace BlurFing.SensorCapture;

internal sealed class MainForm : Form
{
    private readonly TextBox sdk = new() { Dock = DockStyle.Fill, ReadOnly = true, PlaceholderText = "제조사 SDK의 UFScanner.dll을 선택하세요" };
    private readonly Button browse = new() { Text = "SDK DLL 선택", AutoSize = true };
    private readonly Button probe = new() { Text = "장치 확인", AutoSize = true };
    private readonly Button capture = new() { Text = "지문 1장 취득", AutoSize = true };
    private readonly Button cancel = new() { Text = "취소", AutoSize = true, Enabled = false };
    private readonly Button demo = new() { Text = "합성 패턴 테스트", AutoSize = true };
    private readonly Button save = new() { Text = "BMP · PNG · 기록 저장", AutoSize = true, Enabled = false };
    private readonly Button open = new() { Text = "저장 폴더 열기", AutoSize = true };
    private readonly NumericUpDown device = new() { Minimum = 0, Maximum = 99, Width = 60 };
    private readonly NumericUpDown timeout = new() { Minimum = 5, Maximum = 120, Value = 20, Width = 60 };
    private readonly TextBox sample = new() { Text = "sample01", Width = 170, MaxLength = 32 };
    private readonly CheckBox consent = new() { Text = "참여 동의를 받은 연구용 지문만 취득합니다", AutoSize = true };
    private readonly PictureBox picture = new() { Dock = DockStyle.Fill, SizeMode = PictureBoxSizeMode.Zoom, BackColor = Color.FromArgb(236, 240, 244) };
    private readonly Label source = new() { Text = "취득한 영상이 없습니다", Dock = DockStyle.Fill, AutoSize = true, ForeColor = Color.FromArgb(28, 70, 110), Padding = new Padding(8) };
    private readonly TextBox status = new() { Multiline = true, ReadOnly = true, Dock = DockStyle.Fill, ScrollBars = ScrollBars.Vertical, Text = "SDK 없이도 합성 패턴으로 미리보기·저장을 확인할 수 있습니다.\r\n실제 취득에는 제조사 SDK, USB 드라이버, 센서가 필요합니다." };
    private CaptureFrame? frame;
    private CancellationTokenSource? active;
    private bool closeAfterCancel;
    private string? lastSaved;

    public MainForm()
    {
        Text = $"BlurFing | 센서 영상 수집 0.1 · {RuntimeInformation.ProcessArchitecture}";
        Font = new Font("맑은 고딕", 10F);
        ClientSize = new Size(1000, 760);
        MinimumSize = new Size(880, 700);
        StartPosition = FormStartPosition.CenterScreen;
        var layout = new TableLayoutPanel { Dock = DockStyle.Fill, Padding = new Padding(18), ColumnCount = 1, RowCount = 8 };
        layout.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100));
        layout.RowStyles.Add(new RowStyle(SizeType.AutoSize));
        layout.RowStyles.Add(new RowStyle(SizeType.AutoSize));
        layout.RowStyles.Add(new RowStyle(SizeType.AutoSize));
        layout.RowStyles.Add(new RowStyle(SizeType.AutoSize));
        layout.RowStyles.Add(new RowStyle(SizeType.Percent, 100));
        layout.RowStyles.Add(new RowStyle(SizeType.AutoSize));
        layout.RowStyles.Add(new RowStyle(SizeType.Absolute, 104));
        layout.RowStyles.Add(new RowStyle(SizeType.AutoSize));
        var heading = new Label { Text = "BlurFing  /  참조 영상 수집", AutoSize = true, Font = new Font(Font.FontFamily, 20, FontStyle.Bold), Margin = new Padding(0, 0, 0, 14) };
        layout.Controls.Add(heading, 0, 0);
        var sdkRow = new TableLayoutPanel { Dock = DockStyle.Top, AutoSize = true, ColumnCount = 2, Margin = new Padding(0, 0, 0, 10) };
        sdkRow.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100));
        sdkRow.ColumnStyles.Add(new ColumnStyle(SizeType.AutoSize));
        sdkRow.Controls.Add(sdk, 0, 0); sdkRow.Controls.Add(browse, 1, 0);
        layout.Controls.Add(sdkRow, 0, 1);
        var actions = Row();
        actions.Controls.AddRange([probe, new Label { Text = "장치 번호", AutoSize = true, Padding = new Padding(8, 6, 0, 0) }, device,
            new Label { Text = "제한(초)", AutoSize = true, Padding = new Padding(8, 6, 0, 0) }, timeout, capture, cancel, demo]);
        layout.Controls.Add(actions, 0, 2);
        consent.Margin = new Padding(0, 5, 0, 12);
        layout.Controls.Add(consent, 0, 3);
        layout.Controls.Add(picture, 0, 4);
        layout.Controls.Add(source, 0, 5);
        layout.Controls.Add(status, 0, 6);
        var footer = Row();
        footer.Padding = new Padding(0, 8, 0, 0);
        footer.Controls.AddRange([new Label { Text = "익명 ID", AutoSize = true, Padding = new Padding(0, 6, 6, 0) }, sample, save, open]);
        layout.Controls.Add(footer, 0, 7);
        Controls.Add(layout);
        browse.Click += (_, _) => SelectSdk();
        probe.Click += async (_, _) => await AcquireAsync("probe");
        capture.Click += async (_, _) => await AcquireAsync("capture");
        cancel.Click += (_, _) => { active?.Cancel(); SetStatus("취득 프로세스를 종료하는 중입니다…"); };
        demo.Click += (_, _) => { ShowFrame(CaptureFrame.Synthetic()); SetStatus("합성 그라데이션·체커보드입니다. 실제 지문 또는 센서 측정 결과가 아닙니다."); };
        save.Click += (_, _) => SaveFrame();
        open.Click += (_, _) => OpenOutput();
        consent.CheckedChanged += (_, _) => UpdateControls();
        FormClosing += (_, args) =>
        {
            if (active is null) return;
            args.Cancel = true; closeAfterCancel = true; active.Cancel();
        };
        FormClosed += (_, _) => picture.Image?.Dispose();
        UpdateControls();
    }

    private static FlowLayoutPanel Row() => new() { Dock = DockStyle.Top, AutoSize = true, WrapContents = true, Margin = Padding.Empty };
    private void SetStatus(string text) => status.Text = text;

    private void SelectSdk()
    {
        using var dialog = new OpenFileDialog { Title = "신뢰할 수 있는 제조사 SDK의 UFScanner.dll 선택", Filter = "BioMini SDK (UFScanner.dll)|UFScanner.dll", CheckFileExists = true };
        if (dialog.ShowDialog(this) == DialogResult.OK) sdk.Text = dialog.FileName;
        UpdateControls();
    }

    private void UpdateControls()
    {
        var idle = active is null;
        browse.Enabled = demo.Enabled = device.Enabled = timeout.Enabled = consent.Enabled = idle;
        probe.Enabled = idle && File.Exists(sdk.Text);
        capture.Enabled = probe.Enabled && consent.Checked;
        cancel.Enabled = !idle;
        save.Enabled = idle && frame is not null;
        sample.Enabled = idle;
    }

    private void ClearFrame()
    {
        frame = null;
        var previous = picture.Image; picture.Image = null; previous?.Dispose();
        source.Text = "취득한 영상이 없습니다";
    }

    private void ShowFrame(CaptureFrame next)
    {
        var preview = next.CreatePreview();
        var previous = picture.Image; picture.Image = preview; previous?.Dispose();
        frame = next;
        source.Text = next.Source == CaptureSource.Synthetic
            ? $"합성 테스트 패턴 — 실제 지문 아님  |  {next.Width} × {next.Height} px"
            : $"SDK 취득 영상  |  장치 {next.DeviceIndex}  |  {next.Width} × {next.Height} px  |  품질·일치 점수 미측정";
        UpdateControls();
    }

    private async Task AcquireAsync(string operation)
    {
        if (active is not null || (operation == "capture" && !consent.Checked)) return;
        // Do not leave an old/synthetic image looking like the result of a failed real acquisition.
        ClearFrame();
        using var cancellation = new CancellationTokenSource();
        active = cancellation; UpdateControls();
        SetStatus(operation == "probe" ? "SDK 초기화 및 연결 장치 확인 중…" : "센서에 손가락을 올려주세요. 취득 중…");
        try
        {
            var result = await WorkerClient.RunAsync(operation, sdk.Text, (int)device.Value, TimeSpan.FromSeconds((double)timeout.Value), cancellation.Token);
            if (result.Frame is not null) ShowFrame(result.Frame);
            SetStatus(result.Frame is not null ? "취득 완료. 미리보기를 확인한 후 저장하세요. 자동 업로드는 수행하지 않습니다."
                : result.DeviceCount == 0 ? "SDK는 연결됐지만 센서가 없습니다. USB와 드라이버 설치 상태를 확인하세요."
                : $"장치 {result.DeviceCount}개 감지. 번호 0~{result.DeviceCount - 1} 중 선택하세요. 모델명은 조회하지 않았습니다.");
        }
        catch (OperationCanceledException) { SetStatus("취득을 취소했습니다. 저장된 결과는 없습니다."); }
        catch (Exception ex) { SetStatus(ex.Message); }
        finally
        {
            active = null; UpdateControls();
            if (closeAfterCancel) Close();
        }
    }

    private void SaveFrame()
    {
        if (frame is null) return;
        try
        {
            lastSaved = CaptureExport.Save(frame, CaptureExport.DefaultRoot, sample.Text.Trim());
            SetStatus($"저장 완료: {lastSaved}\r\nBMP 원본, PNG 사본, metadata.json. 개인 지문은 공개 GitHub에 올리지 마세요.");
        }
        catch (Exception ex) { SetStatus($"저장 실패: {ex.Message}"); }
    }

    private void OpenOutput()
    {
        try
        {
            Directory.CreateDirectory(CaptureExport.DefaultRoot);
            Process.Start(new ProcessStartInfo(lastSaved ?? CaptureExport.DefaultRoot) { UseShellExecute = true });
        }
        catch (Exception ex) { SetStatus($"폴더 열기 실패: {ex.Message}"); }
    }
}
