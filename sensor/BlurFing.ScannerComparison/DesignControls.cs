using System.Drawing.Drawing2D;
using System.ComponentModel;

namespace BlurFing.ScannerComparison;

internal static class Design
{
    internal static readonly Color Canvas = Color.FromArgb(240, 245, 247);
    internal static readonly Color Ink = Color.FromArgb(20, 46, 59);
    internal static readonly Color Muted = Color.FromArgb(82, 108, 122);
    internal static readonly Color Accent = Color.FromArgb(8, 116, 128);
    internal static readonly Color AccentSoft = Color.FromArgb(224, 241, 242);
    internal static readonly Color Border = Color.FromArgb(217, 229, 233);

    internal static GraphicsPath Rounded(RectangleF rectangle, float radius)
    {
        var path = new GraphicsPath(); var d = Math.Min(radius * 2, Math.Min(rectangle.Width, rectangle.Height));
        path.AddArc(rectangle.X, rectangle.Y, d, d, 180, 90);
        path.AddArc(rectangle.Right - d, rectangle.Y, d, d, 270, 90);
        path.AddArc(rectangle.Right - d, rectangle.Bottom - d, d, d, 0, 90);
        path.AddArc(rectangle.X, rectangle.Bottom - d, d, d, 90, 90); path.CloseFigure(); return path;
    }

    internal static void Fingerprint(Graphics graphics, RectangleF rectangle, Color color)
    {
        using var pen = new Pen(color, Math.Max(1.4f, rectangle.Width / 30)) { StartCap = LineCap.Round, EndCap = LineCap.Round };
        for (var i = 0; i < 6; i++)
        {
            var inset = rectangle.Width * i * .065f;
            var arc = new RectangleF(rectangle.X + inset, rectangle.Y + inset * .8f,
                rectangle.Width - inset * 2, rectangle.Height - inset * 1.5f);
            graphics.DrawArc(pen, arc, 145, 265);
        }
    }
}

internal sealed class DesignCard : Panel
{
    [DesignerSerializationVisibility(DesignerSerializationVisibility.Hidden)]
    internal Color Fill { get; set; } = Color.White;
    [DesignerSerializationVisibility(DesignerSerializationVisibility.Hidden)]
    internal int Radius { get; set; } = 18;
    internal DesignCard()
    {
        DoubleBuffered = true; BackColor = Design.Canvas; Padding = new Padding(16); Margin = new Padding(0, 0, 0, 12);
    }
    protected override void OnPaint(PaintEventArgs e)
    {
        base.OnPaint(e); if (Width < 2 || Height < 2) return;
        e.Graphics.SmoothingMode = SmoothingMode.AntiAlias;
        using var path = Design.Rounded(new RectangleF(.5f, .5f, Width - 1, Height - 1), Radius);
        using var fill = new SolidBrush(Fill); using var border = new Pen(Design.Border);
        e.Graphics.FillPath(fill, path); e.Graphics.DrawPath(border, path);
    }
}

internal sealed class DesignButton : Button
{
    private readonly bool primary;
    private bool hover;
    internal DesignButton(bool primary = false)
    {
        this.primary = primary; AutoSize = true; MinimumSize = new Size(90, primary ? 50 : 42);
        Padding = new Padding(16, 8, 16, 8); Margin = new Padding(0, 0, 10, 0);
        Font = new Font("맑은 고딕", 10, primary ? FontStyle.Bold : FontStyle.Regular);
        FlatStyle = FlatStyle.Flat; FlatAppearance.BorderSize = 0;
        SetStyle(ControlStyles.UserPaint | ControlStyles.AllPaintingInWmPaint | ControlStyles.OptimizedDoubleBuffer, true);
    }
    public override Size GetPreferredSize(Size proposedSize)
    {
        var text = TextRenderer.MeasureText(Text, Font);
        return new Size(Math.Max(MinimumSize.Width, text.Width + Padding.Horizontal + 12), Math.Max(MinimumSize.Height, text.Height + Padding.Vertical));
    }
    protected override void OnMouseEnter(EventArgs e) { hover = true; Invalidate(); base.OnMouseEnter(e); }
    protected override void OnMouseLeave(EventArgs e) { hover = false; Invalidate(); base.OnMouseLeave(e); }
    protected override void OnGotFocus(EventArgs e) { Invalidate(); base.OnGotFocus(e); }
    protected override void OnLostFocus(EventArgs e) { Invalidate(); base.OnLostFocus(e); }
    protected override void OnPaint(PaintEventArgs e)
    {
        e.Graphics.SmoothingMode = SmoothingMode.AntiAlias;
        var background = !Enabled ? Color.FromArgb(229, 236, 239) : primary
            ? (hover ? Color.FromArgb(5, 93, 104) : Design.Accent) : (hover ? Design.AccentSoft : Color.White);
        var foreground = !Enabled ? Color.FromArgb(122, 144, 154) : primary ? Color.White : Design.Ink;
        using var path = Design.Rounded(new RectangleF(1, 1, Width - 3, Height - 3), 13);
        using var brush = new SolidBrush(background); e.Graphics.FillPath(brush, path);
        if (!primary) { using var pen = new Pen(Design.Border); e.Graphics.DrawPath(pen, path); }
        if (Focused && ShowFocusCues) { using var pen = new Pen(primary ? Color.White : Design.Accent, 2); using var focus = Design.Rounded(new RectangleF(4, 4, Width - 9, Height - 9), 10); e.Graphics.DrawPath(pen, focus); }
        TextRenderer.DrawText(e.Graphics, Text, Font, ClientRectangle, foreground,
            TextFormatFlags.HorizontalCenter | TextFormatFlags.VerticalCenter | TextFormatFlags.SingleLine | TextFormatFlags.EndEllipsis);
    }
}

internal sealed class BrandMark : Control
{
    internal BrandMark() { DoubleBuffered = true; Size = new Size(58, 58); }
    protected override void OnPaint(PaintEventArgs e)
    {
        base.OnPaint(e); e.Graphics.SmoothingMode = SmoothingMode.AntiAlias;
        using var path = Design.Rounded(new RectangleF(0, 0, Width - 1, Height - 1), 17);
        using var brush = new SolidBrush(Design.Accent); e.Graphics.FillPath(brush, path);
        Design.Fingerprint(e.Graphics, new RectangleF(14, 11, Width - 28, Height - 23), Color.White);
    }
}

internal sealed class PreviewBox : PictureBox
{
    [DesignerSerializationVisibility(DesignerSerializationVisibility.Hidden)]
    internal string EmptyText { get; set; } = "새 지문을 기다리고 있어요";
    internal PreviewBox() { DoubleBuffered = true; BackColor = Color.FromArgb(246, 249, 250); }
    protected override void OnPaint(PaintEventArgs pe)
    {
        base.OnPaint(pe); if (Image is not null) return;
        pe.Graphics.SmoothingMode = SmoothingMode.AntiAlias;
        var compact = Height < 150;
        var glyphHeight = Math.Min(66, Math.Max(20, Height - 16));
        var glyphWidth = glyphHeight * 50 / 66;
        var middle = new RectangleF((Width - glyphWidth) / 2f, compact ? (Height - glyphHeight) / 2f : Height / 2f - 55, glyphWidth, glyphHeight);
        Design.Fingerprint(pe.Graphics, middle, Color.FromArgb(169, 192, 199));
        if (!compact) TextRenderer.DrawText(pe.Graphics, EmptyText, Font, new Rectangle(8, (int)middle.Bottom + 18, Width - 16, 45),
                Design.Muted, TextFormatFlags.HorizontalCenter | TextFormatFlags.WordBreak);
    }
}
