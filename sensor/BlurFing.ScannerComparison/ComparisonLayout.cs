namespace BlurFing.ScannerComparison;

internal sealed partial class ComparisonForm
{
    private readonly Label stateBadge = new() { AutoSize = true, Padding = new Padding(14, 9, 14, 9),
        BackColor = Design.AccentSoft, ForeColor = Design.Accent };

    private void InitializeDesign()
    {
        Text = "BlurFing 0.3.1 | 센서 지문 비교"; Font = new Font("맑은 고딕", 10);
        ClientSize = new Size(1280, 860); MinimumSize = new Size(1080, 770);
        StartPosition = FormStartPosition.CenterScreen; BackColor = Design.Canvas; ForeColor = Design.Ink; DoubleBuffered = true;
        var layout = new TableLayoutPanel { Dock = DockStyle.Fill, BackColor = Design.Canvas, Padding = new Padding(24, 20, 24, 16), ColumnCount = 1, RowCount = 7 };
        layout.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100));
        layout.RowStyles.Add(new RowStyle(SizeType.Absolute, 108));
        layout.RowStyles.Add(new RowStyle(SizeType.Absolute, 146));
        layout.RowStyles.Add(new RowStyle(SizeType.Absolute, 66));
        layout.RowStyles.Add(new RowStyle(SizeType.AutoSize));
        layout.RowStyles.Add(new RowStyle(SizeType.Percent, 100));
        layout.RowStyles.Add(new RowStyle(SizeType.Absolute, 108));
        layout.RowStyles.Add(new RowStyle(SizeType.Absolute, 26));

        var header = new TableLayoutPanel { Dock = DockStyle.Fill, ColumnCount = 3, BackColor = Design.Canvas };
        header.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute, 76)); header.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100)); header.ColumnStyles.Add(new ColumnStyle(SizeType.AutoSize));
        header.Controls.Add(new BrandMark { Margin = new Padding(0, 4, 0, 0) }, 0, 0);
        var wordmark = new FlowLayoutPanel { Dock = DockStyle.Fill, FlowDirection = FlowDirection.TopDown, WrapContents = false, Margin = Padding.Empty };
        wordmark.Controls.Add(new Label { Text = "BlurFing  /  지문 비교", AutoSize = true, Font = new Font(Font.FontFamily, 22, FontStyle.Bold), ForeColor = Design.Ink, Margin = Padding.Empty });
        wordmark.Controls.Add(new Label { Text = "센서 원본과 AI 처리본을 한눈에 비교하세요", AutoSize = true, ForeColor = Design.Muted, Margin = new Padding(0, 5, 0, 0) });
        header.Controls.Add(wordmark, 1, 0); stateBadge.Anchor = AnchorStyles.Right | AnchorStyles.Top; stateBadge.Margin = new Padding(0, 12, 0, 0); header.Controls.Add(stateBadge, 2, 0);
        layout.Controls.Add(header, 0, 0);

        var connectionCard = new DesignCard { Dock = DockStyle.Fill, Padding = new Padding(16, 10, 16, 8) };
        var connection = new TableLayoutPanel { Dock = DockStyle.Fill, BackColor = Color.White, ColumnCount = 3, RowCount = 3 };
        connection.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100)); connection.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute, 110)); connection.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute, 10));
        connection.RowStyles.Add(new RowStyle(SizeType.Absolute, 22)); connection.RowStyles.Add(new RowStyle(SizeType.Absolute, 40)); connection.RowStyles.Add(new RowStyle(SizeType.Percent, 100));
        connection.Controls.Add(new Label { Text = "처리 서버", AutoSize = true, ForeColor = Design.Muted, Font = new Font(Font.FontFamily, 9, FontStyle.Bold) }, 0, 0);
        var field = new Panel { Dock = DockStyle.Fill, BackColor = Design.Canvas, Padding = new Padding(10, 7, 10, 5), Margin = new Padding(0, 0, 12, 0) };
        field.Paint += (_, e) =>
        {
            e.Graphics.SmoothingMode = System.Drawing.Drawing2D.SmoothingMode.AntiAlias;
            using var edge = Design.Rounded(new RectangleF(.5f, .5f, field.Width - 1, field.Height - 1), 9);
            using var pen = new Pen(address.Focused ? Design.Accent : Color.FromArgb(115, 139, 151), address.Focused ? 2 : 1);
            e.Graphics.DrawPath(pen, edge);
        };
        address.Enter += (_, _) => field.Invalidate(); address.Leave += (_, _) => field.Invalidate();
        address.BorderStyle = BorderStyle.None; address.BackColor = Design.Canvas; address.ForeColor = Design.Ink; field.Controls.Add(address);
        connection.Controls.Add(field, 0, 1); check.Dock = DockStyle.Fill; check.Margin = Padding.Empty; connection.Controls.Add(check, 1, 1);
        consent.ForeColor = Design.Ink; consent.BackColor = Design.AccentSoft; consent.Padding = new Padding(8, 3, 8, 3); consent.Dock = DockStyle.Fill;
        consent.Margin = new Padding(0, 6, 0, 0); connection.Controls.Add(consent, 0, 2); connection.SetColumnSpan(consent, 2);
        connectionCard.Controls.Add(connection); layout.Controls.Add(connectionCard, 0, 1);

        var actions = Row(); actions.Padding = new Padding(0, 3, 0, 8); capture.MinimumSize = new Size(270, 50);
        var tools = new DesignButton { Text = "추가 도구 보기" };
        actions.Controls.AddRange([capture, export, cancel, tools]); layout.Controls.Add(actions, 0, 2);
        var extras = new DesignCard { Name = "advancedTools", Dock = DockStyle.Top, Height = 128, Visible = false, Padding = new Padding(12) };
        var extraRow = Row(); extraRow.AutoSize = false; extraRow.AutoScroll = true; extraRow.BackColor = Color.White;
        extraRow.Controls.AddRange([import, compare, configureFfv, preview, new Label { Text = "DPI", AutoSize = true, Padding = new Padding(4, 10, 0, 0) }, dpi]);
        extraRow.Controls.Add(automatic); extras.Controls.Add(extraRow); layout.Controls.Add(extras, 0, 3);
        tools.Click += (_, _) => { extras.Visible = !extras.Visible; tools.Text = extras.Visible ? "추가 도구 접기" : "추가 도구 보기"; };

        var columns = new TableLayoutPanel { Dock = DockStyle.Fill, ColumnCount = 3, Padding = new Padding(0, 0, 0, 10), Margin = Padding.Empty };
        columns.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 37)); columns.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 37)); columns.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 26));
        columns.Controls.Add(ImagePanel("01  센서 원본", original, origin), 0, 0);
        columns.Controls.Add(ImagePanel("02  AI 처리본", processed, protection), 1, 0);
        var scores = new DesignCard { Dock = DockStyle.Fill, Padding = new Padding(20), Margin = new Padding(8, 0, 0, 0) };
        var scoreLayout = new TableLayoutPanel { Dock = DockStyle.Fill, RowCount = 4, BackColor = Color.White };
        scoreLayout.RowStyles.Add(new RowStyle(SizeType.Absolute, 30)); scoreLayout.RowStyles.Add(new RowStyle(SizeType.Absolute, 82)); scoreLayout.RowStyles.Add(new RowStyle(SizeType.Absolute, 32)); scoreLayout.RowStyles.Add(new RowStyle(SizeType.Percent, 100));
        score.Font = new Font("Segoe UI", 32, FontStyle.Bold); score.ForeColor = Design.Accent; score.Dock = DockStyle.Fill;
        scoreDetail.Font = new Font(Font.FontFamily, 9); scoreDetail.ForeColor = Design.Muted; scoreDetail.Padding = new Padding(0, 8, 0, 0); scoreDetail.Dock = DockStyle.Top;
        var detailScroll = new Panel { Dock = DockStyle.Fill, AutoScroll = true, BackColor = Color.White };
        detailScroll.Controls.Add(scoreDetail);
        detailScroll.SizeChanged += (_, _) => scoreDetail.MaximumSize = new Size(Math.Max(80, detailScroll.ClientSize.Width - SystemInformation.VerticalScrollBarWidth), 0);
        scoreLayout.Controls.Add(new Label { Text = "03  전후 유사도", AutoSize = true, Font = new Font(Font, FontStyle.Bold) }, 0, 0); scoreLayout.Controls.Add(score, 0, 1);
        scoreLayout.Controls.Add(new Label { Text = "100점 환산 · 높을수록 유사", AutoSize = true, ForeColor = Design.Muted }, 0, 2); scoreLayout.Controls.Add(detailScroll, 0, 3);
        scores.Controls.Add(scoreLayout); columns.Controls.Add(scores, 2, 0); layout.Controls.Add(columns, 0, 4);

        var statusCard = new DesignCard { Dock = DockStyle.Fill, Padding = new Padding(16, 12, 16, 10), Margin = new Padding(0, 0, 0, 10) };
        var messages = new TableLayoutPanel { Dock = DockStyle.Fill, RowCount = 2, BackColor = Color.White };
        messages.RowStyles.Add(new RowStyle(SizeType.Absolute, 23)); messages.RowStyles.Add(new RowStyle(SizeType.Percent, 100));
        messages.Controls.Add(new Label { Text = "진행 상태", AutoSize = true, Font = new Font(Font.FontFamily, 9, FontStyle.Bold), ForeColor = Design.Muted }, 0, 0);
        status.BorderStyle = BorderStyle.None; status.BackColor = Color.White; status.ForeColor = Design.Ink; status.Font = new Font(Font.FontFamily, 9);
        messages.Controls.Add(status, 0, 1); statusCard.Controls.Add(messages); layout.Controls.Add(statusCard, 0, 5);
        layout.Controls.Add(new Label { Text = "연구용 비교 도구 · 100점 환산 지수는 확률·인식률이 아니며, 점수 감소만으로 보호 성공을 판단하지 않습니다.", AutoSize = true, ForeColor = Design.Muted, Font = new Font(Font.FontFamily, 8.5f), Dock = DockStyle.Fill }, 0, 6);
        Controls.Add(layout);
    }

    private void UpdateDesignState()
    {
        stateBadge.Text = active is not null ? (capturePending && input is null ? "지문 취득 중" : "서버 처리 중")
            : result is not null ? "비교 완료" : input?.Synthetic == true ? "합성 화면 예시" : input is not null ? "원본 준비됨" : "새 취득 대기";
    }

    internal void RenderDesignPreview(string path, bool sample = true, bool tools = false, double? exampleScore = null)
    {
        address.Text = "https://school-server.example/scanner/";
        if (sample) { ShowSynthetic(); consent.Checked = true; }
        if (exampleScore is { } raw)
        {
            score.Text = MatchScoreScale.Format(raw);
            scoreDetail.Text = $"원시 점수 예시: {raw.ToString(System.Globalization.CultureInfo.InvariantCulture)}\n합성 환산 예시 · 실측 아님\n\n환산: 100 × s / (s + 40)\n40점 → 환산 50점\n확률·인식률 아님";
            status.Text = "합성 화면·환산식 확인용 예시입니다. 실제 센서·AI 매칭 결과가 아닙니다.";
        }
        if (tools) Controls.Find("advancedTools", true)[0].Visible = true;
        // Render our own control tree, without displaying a window or attaching
        // the live capture listener. No desktop/window screenshot is taken.
        var content = Controls[0]; Controls.Remove(content); content.Size = ClientSize;
        void Arrange(Control control) { control.CreateControl(); control.PerformLayout(); foreach (Control child in control.Controls) Arrange(child); }
        using (content)
        {
            Arrange(content); content.PerformLayout();
            using var bitmap = new Bitmap(content.Width, content.Height); content.DrawToBitmap(bitmap, new Rectangle(Point.Empty, content.Size));
            Directory.CreateDirectory(Path.GetDirectoryName(Path.GetFullPath(path))!); bitmap.Save(path, System.Drawing.Imaging.ImageFormat.Png);
        }
    }
}
