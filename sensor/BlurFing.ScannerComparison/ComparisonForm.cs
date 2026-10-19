using System.Diagnostics;
using System.Text.Json;

namespace BlurFing.ScannerComparison;

internal sealed class ComparisonForm : Form
{
    private readonly TextBox address = new() { Dock = DockStyle.Fill, PlaceholderText = "Ubuntu 센서 비교 서버의 HTTPS 주소" };
    private readonly NumericUpDown dpi = new() { Minimum = 100, Maximum = 2000, Value = 500, Width = 75 };
    private readonly Button check = new() { Text = "서버 확인", AutoSize = true };
    private readonly Button import = new() { Text = "저장한 센서 영상 열기", AutoSize = true };
    private readonly Button compare = new() { Text = "서버 AI 처리 · 매칭", AutoSize = true };
    private readonly Button cancel = new() { Text = "처리 취소", AutoSize = true, Enabled = false };
    private readonly Button export = new() { Text = "3열 비교 자료 저장", AutoSize = true, Enabled = false };
    private readonly Button preview = new() { Text = "합성 화면 확인", AutoSize = true };
    private readonly CheckBox consent = new() { Text = "선택한 서버로 연구용 지문 영상 전송", AutoSize = true };
    private readonly CheckBox automatic = new() { Text = "FFV 새 취득 후 자동 처리", AutoSize = true };
    private readonly PictureBox original = new() { Dock = DockStyle.Fill, SizeMode = PictureBoxSizeMode.Zoom, BackColor = Color.FromArgb(239, 243, 248) };
    private readonly PictureBox processed = new() { Dock = DockStyle.Fill, SizeMode = PictureBoxSizeMode.Zoom, BackColor = Color.FromArgb(239, 243, 248) };
    private readonly Label origin = new() { Text = "FFV 새 취득 대기", AutoSize = true, Dock = DockStyle.Fill, Padding = new Padding(8) };
    private readonly Label protection = new() { Text = "아직 처리하지 않았습니다", AutoSize = true, Dock = DockStyle.Fill, Padding = new Padding(8) };
    private readonly Label score = new() { Text = "미측정", AutoSize = true, Font = new Font("Segoe UI", 36, FontStyle.Bold), ForeColor = Color.FromArgb(61, 65, 135) };
    private readonly Label scoreDetail = new() { Text = "SourceAFIS 원시 유사도 점수\n\n원본과 AI 처리본을 비교합니다.\n백분율·본인 일치 확률이 아닙니다.", AutoSize = true, MaximumSize = new Size(270, 0), Padding = new Padding(0, 12, 0, 0) };
    private readonly TextBox status = new() { Multiline = true, ReadOnly = true, Dock = DockStyle.Fill, ScrollBars = ScrollBars.Vertical };
    private readonly CancellationTokenSource lifetime = new();
    private CancellationTokenSource? active;
    private long generation;
    private long incomingSequence;
    private ScannerInput? input;
    private ScannerResult? result;
    private string? lastExport;
    private static string SettingsPath => Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "BlurFing", "ScannerComparison", "settings.json");

    public ComparisonForm(bool showPreview = false)
    {
        Text = "BlurFing | FFV 센서 · 서버 AI · 매칭 비교";
        Font = new Font("맑은 고딕", 10);
        ClientSize = new Size(1240, 800); MinimumSize = new Size(1040, 720);
        StartPosition = FormStartPosition.CenterScreen;
        BackColor = Color.White;
        var layout = new TableLayoutPanel { Dock = DockStyle.Fill, Padding = new Padding(20), ColumnCount = 1, RowCount = 7 };
        foreach (var size in new[] { 60, 44, 42, 40 }) layout.RowStyles.Add(new RowStyle(SizeType.Absolute, size));
        layout.RowStyles.Add(new RowStyle(SizeType.Percent, 100));
        layout.RowStyles.Add(new RowStyle(SizeType.Absolute, 100));
        layout.RowStyles.Add(new RowStyle(SizeType.Absolute, 35));
        layout.Controls.Add(new Label { Text = "FFV 지문  /  AI 처리와 매칭 비교", AutoSize = true,
            Font = new Font(Font.FontFamily, 22, FontStyle.Bold), ForeColor = Color.FromArgb(29, 44, 65) }, 0, 0);
        var server = new TableLayoutPanel { Dock = DockStyle.Fill, ColumnCount = 4 };
        server.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute, 90)); server.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100));
        server.ColumnStyles.Add(new ColumnStyle(SizeType.AutoSize)); server.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute, 190));
        server.Controls.Add(new Label { Text = "비교 서버", AutoSize = true, Padding = new Padding(0, 6, 0, 0) }, 0, 0);
        server.Controls.Add(address, 1, 0); server.Controls.Add(check, 2, 0);
        var resolution = Row(); resolution.Controls.AddRange([new Label { Text = "설정 DPI", AutoSize = true, Padding = new Padding(6, 6, 0, 0) }, dpi]);
        server.Controls.Add(resolution, 3, 0); layout.Controls.Add(server, 0, 1);
        var approvals = Row(); approvals.Controls.AddRange([consent, automatic]); layout.Controls.Add(approvals, 0, 2);
        var actions = Row(); actions.Controls.AddRange([import, compare, cancel, export, preview]); layout.Controls.Add(actions, 0, 3);
        var columns = new TableLayoutPanel { Dock = DockStyle.Fill, ColumnCount = 3, Padding = new Padding(0, 10, 0, 10) };
        columns.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 37)); columns.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 37)); columns.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 26));
        columns.Controls.Add(ImagePanel("01  센서 원본", original, origin), 0, 0);
        columns.Controls.Add(ImagePanel("02  서버 AI 처리본", processed, protection), 1, 0);
        var scores = new FlowLayoutPanel { Dock = DockStyle.Fill, FlowDirection = FlowDirection.TopDown, WrapContents = false, Padding = new Padding(15), BackColor = Color.FromArgb(245, 246, 252) };
        scores.Controls.AddRange([new Label { Text = "03  원본 ↔ 처리본 매칭", AutoSize = true, Font = new Font(Font, FontStyle.Bold) }, score, scoreDetail]);
        columns.Controls.Add(scores, 2, 0); layout.Controls.Add(columns, 0, 4); layout.Controls.Add(status, 0, 5);
        layout.Controls.Add(new Label { Text = "실험 처리입니다. 점수 감소·특징 추출 실패만으로 지문 보호 성공을 판단하지 않습니다.", Dock = DockStyle.Fill, ForeColor = Color.DimGray, AutoSize = true }, 0, 6);
        Controls.Add(layout);
        LoadSettings();
        address.TextChanged += (_, _) => { consent.Checked = false; automatic.Checked = false; UpdateControls(); };
        consent.CheckedChanged += (_, _) => { if (!consent.Checked) automatic.Checked = false; UpdateControls(); };
        import.Click += (_, _) => ImportImage();
        preview.Click += (_, _) => ShowSynthetic();
        check.Click += async (_, _) => await CheckServer();
        compare.Click += async (_, _) => await Compare();
        cancel.Click += (_, _) => { generation++; active?.Cancel(); active = null; status.Text = "처리를 취소했습니다. 원본은 유지됩니다."; UpdateControls(); };
        export.Click += (_, _) => Export();
        FormClosing += (_, _) => { generation++; active?.Cancel(); lifetime.Cancel(); };
        FormClosed += (_, _) => { original.Image?.Dispose(); processed.Image?.Dispose(); lifetime.Dispose(); };
        Shown += (_, _) =>
        {
            if (showPreview) ShowSynthetic();
            _ = FfvReceiver.ListenAsync(async png =>
            {
                var incoming = Interlocked.Increment(ref incomingSequence);
                try
                {
                    if (!IsDisposed && !lifetime.IsCancellationRequested) BeginInvoke(() =>
                    {
                        if (incoming != Interlocked.Read(ref incomingSequence)) return;
                        generation++; active?.Cancel(); active = null; ClearResult(); UpdateControls();
                        origin.Text = "FFV 새 영상을 확인하는 중입니다…";
                    });
                    var next = await Task.Run(() => ScannerInput.Decode(png, "FFV 연동 새 취득 영상"));
                    if (!IsDisposed && !lifetime.IsCancellationRequested) BeginInvoke(async () =>
                    {
                        if (incoming != Interlocked.Read(ref incomingSequence)) return;
                        UseInput(next);
                        status.Text = "FFV 새 영상을 받았습니다. " + (automatic.Checked && consent.Checked ? "서버 처리를 시작합니다." : "서버 전송을 선택한 후 처리할 수 있습니다.");
                        if (automatic.Checked && consent.Checked) await Compare();
                    });
                }
                catch (Exception) { if (!IsDisposed && !lifetime.IsCancellationRequested) BeginInvoke(() =>
                {
                    if (incoming != Interlocked.Read(ref incomingSequence)) return;
                    ClearResult(); origin.Text = "새 FFV 영상 읽기 실패 · 이전 원본 유지";
                    status.Text = "FFV 영상 형식·크기를 확인해 주세요. 새 처리본과 점수는 없습니다."; UpdateControls();
                }); }
            }, lifetime.Token);
        };
        status.Text = "FFV 확장의 Send to comparison을 켠 뒤 새로 취득하세요. 저장한 PNG/BMP도 열 수 있습니다.\r\n서버 확인은 설정만 검사합니다. 실제 AI·매칭 실행 확인은 영상을 처리한 뒤 가능합니다.";
        UpdateControls();
    }

    private static FlowLayoutPanel Row() => new() { Dock = DockStyle.Fill, AutoSize = true, WrapContents = true };
    private static Control ImagePanel(string title, PictureBox image, Label caption)
    {
        var panel = new TableLayoutPanel { Dock = DockStyle.Fill, RowCount = 3, Padding = new Padding(5) };
        panel.RowStyles.Add(new RowStyle(SizeType.Absolute, 34)); panel.RowStyles.Add(new RowStyle(SizeType.Percent, 100)); panel.RowStyles.Add(new RowStyle(SizeType.Absolute, 80));
        panel.Controls.Add(new Label { Text = title, AutoSize = true, Font = new Font("맑은 고딕", 12, FontStyle.Bold) }, 0, 0);
        panel.Controls.Add(image, 0, 1); panel.Controls.Add(caption, 0, 2); return panel;
    }

    private void UpdateControls()
    {
        compare.Enabled = input is not null && consent.Checked && active is null;
        cancel.Enabled = active is not null; export.Enabled = result is not null && active is null;
        consent.Enabled = active is null; automatic.Enabled = consent.Checked && active is null; check.Enabled = active is null;
        address.Enabled = dpi.Enabled = active is null;
    }
    private void ClearResult()
    {
        result = null; processed.Image?.Dispose(); processed.Image = null; score.Text = "미측정";
        protection.Text = "아직 처리하지 않았습니다";
        scoreDetail.Text = "SourceAFIS 원시 유사도 점수\n\n원본과 AI 처리본을 비교합니다.\n백분율·본인 일치 확률이 아닙니다.";
    }
    private void UseInput(ScannerInput next)
    {
        Interlocked.Increment(ref incomingSequence); generation++; active?.Cancel(); active = null; ClearResult();
        input = next; original.Image?.Dispose(); original.Image = next.Preview();
        origin.Text = $"{next.Origin}\n{next.Width} × {next.Height} px · 원본 해상도";
        UpdateControls();
    }
    private void ShowSynthetic()
    {
        var pattern = ScannerInput.SyntheticPattern(); UseInput(pattern);
        processed.Image = pattern.Preview(); protection.Text = "합성 화면 예시 · AI 처리 결과 아님";
        status.Text = "화면 배치 확인용 합성 패턴입니다. 실제 지문·AI 처리·매칭 점수를 생성하지 않았습니다.";
    }
    private void ImportImage()
    {
        using var dialog = new OpenFileDialog { Filter = "회색조 센서 영상|*.png;*.bmp", Title = "FFV에서 저장한 원본 영상 선택" };
        if (dialog.ShowDialog(this) != DialogResult.OK) return;
        try
        {
            if (new FileInfo(dialog.FileName).Length > ScannerInput.MaxBytes) throw new InvalidDataException("파일은 4MiB 이하여야 합니다.");
            UseInput(ScannerInput.Decode(File.ReadAllBytes(dialog.FileName), "불러온 센서 영상 · 실시간 취득 확인 아님"));
            status.Text = "영상을 불러왔습니다. 원본 파일은 변경하지 않았습니다.";
        }
        catch (Exception) { status.Text = "회색조 PNG/BMP·파일 크기·해상도를 확인해 주세요."; }
    }
    private async Task CheckServer()
    {
        try
        {
            var checkedAddress = address.Text;
            using var client = new ScannerClient(address.Text);
            using var deadline = new CancellationTokenSource(TimeSpan.FromSeconds(30));
            check.Enabled = false; await client.CheckAsync(deadline.Token);
            if (address.Text != checkedAddress) return;
            SaveSettings(); status.Text = "센서 비교 서버의 설정을 확인했습니다. 실제 추론·매칭 성공을 뜻하지는 않습니다.";
        }
        catch (Exception error) { status.Text = SafeMessage(error); }
        finally { UpdateControls(); }
    }
    private async Task Compare()
    {
        if (input is null || !consent.Checked || active is not null) return;
        var source = input; var token = ++generation; var configuredDpi = (int)dpi.Value;
        using var cancellation = CancellationTokenSource.CreateLinkedTokenSource(lifetime.Token);
        active = cancellation; ClearResult(); UpdateControls();
        status.Text = source.Synthetic ? "합성 자료를 서버에서 처리합니다. 실제 센서 성능 시험이 아닙니다." : "서버에서 실험 처리와 SourceAFIS 매칭 중입니다…";
        try
        {
            using var client = new ScannerClient(address.Text); SaveSettings();
            var reply = await client.CompareAsync(source, Guid.NewGuid().ToString("N"), configuredDpi, cancellation.Token);
            if (token != generation || !ReferenceEquals(input, source) || cancellation.IsCancellationRequested) return;
            using var stream = new MemoryStream(reply.Png); using var image = Image.FromStream(stream);
            processed.Image = new Bitmap(image); result = reply; protection.Text = $"{reply.StatusText}\n변경 {reply.ChangedPixels:N0} 픽셀";
            score.Text = reply.ScoreText;
            scoreDetail.Text = $"SourceAFIS {reply.EngineVersion ?? "미준비"}\n설정 DPI {reply.Dpi}\n원본 특징점 {reply.ProbeMinutiae?.ToString() ?? "미측정"}\n처리본 특징점 {reply.CandidateMinutiae?.ToString() ?? "미측정"}\n\n{(reply.MatchStatus == "measured" ? "원본 ↔ AI 처리본 직접 비교" : reply.MatchStatus == "unmeasurable" ? "특징점이 없어 측정 불가" : "매칭 실행 환경 미준비·실행 실패")}\n\n확률·백분율 아님";
            status.Text = $"검증된 현재 요청 결과를 표시했습니다. 서버 처리 {reply.ProcessingMs:N0}ms.\r\n원본·처리본·비교 기록과 hstack.png를 저장할 수 있습니다.";
        }
        catch (Exception error) { if (token == generation && !IsDisposed) status.Text = SafeMessage(error); }
        finally { if (ReferenceEquals(active, cancellation)) active = null; if (!IsDisposed) UpdateControls(); }
    }
    private static string SafeMessage(Exception error) => error switch
    {
        OperationCanceledException => "요청을 취소했거나 응답 시간이 초과됐습니다. 원본은 유지됩니다.",
        ArgumentException or InvalidOperationException => error.Message,
        _ => "서버 연결·반환 영상·매칭 정보 검증에 실패했습니다. 원본은 유지됩니다."
    };
    private void LoadSettings()
    {
        try
        {
            using var json = JsonDocument.Parse(File.ReadAllText(SettingsPath));
            address.Text = json.RootElement.GetProperty("address").GetString();
            dpi.Value = Math.Clamp(json.RootElement.GetProperty("dpi").GetInt32(), 100, 2000);
        }
        catch (Exception) { address.Text = "http://127.0.0.1:8002"; }
    }
    private void SaveSettings()
    {
        Directory.CreateDirectory(Path.GetDirectoryName(SettingsPath)!);
        File.WriteAllText(SettingsPath, JsonSerializer.Serialize(new { address = address.Text.Trim(), dpi = (int)dpi.Value }));
    }
    private void Export()
    {
        if (input is null || result is null) return;
        using var dialog = new FolderBrowserDialog { Description = "공개 Git 밖의 개인 비교 자료 저장 폴더", UseDescriptionForTitle = true };
        if (dialog.ShowDialog(this) != DialogResult.OK) return;
        try { lastExport = ComparisonExport.Save(dialog.SelectedPath, input, result); status.Text = "비교 자료 저장 완료: " + lastExport; }
        catch (Exception) { status.Text = "비교 자료를 저장하지 못했습니다. 저장 위치와 공간을 확인해 주세요."; }
    }
}
