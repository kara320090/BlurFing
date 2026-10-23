using System.Drawing.Imaging;
using System.Text.Json;

namespace BlurFing.ScannerComparison;

internal static class ComparisonExport
{
    public static string Save(string parent, ScannerInput input, ScannerResult result)
    {
        var folder = Path.Combine(Path.GetFullPath(parent), "comparison-" + DateTime.UtcNow.ToString("yyyyMMdd-HHmmss") + "-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(folder);
        File.WriteAllBytes(Path.Combine(folder, "original.png"), input.Png);
        File.WriteAllBytes(Path.Combine(folder, "processed.png"), result.Png);
        var receipt = new
        {
            schema_version = "scanner-comparison-v1", request_id = result.RequestId, input_synthetic = input.Synthetic,
            input_origin = input.Origin,
            source_sha256 = input.Sha, source_pixel_sha256 = input.PixelSha, processed_sha256 = ScannerInput.Hash(result.Png),
            width = input.Width, height = input.Height, protection_status = result.ProtectionStatus,
            changed_pixels = result.ChangedPixels, matcher = "SourceAFIS", matcher_version = result.EngineVersion,
            match_status = result.MatchStatus, similarity_score = result.Score, configured_dpi = result.Dpi,
            similarity_index_100 = result.Score100, similarity_index_method = MatchScoreScale.Method,
            similarity_index_reference = MatchScoreScale.Reference, similarity_index_formula = MatchScoreScale.Formula,
            similarity_index_unit = "display_index_out_of_100_not_probability",
            probe_minutiae = result.ProbeMinutiae, candidate_minutiae = result.CandidateMinutiae,
            measured_at = result.MeasuredAt, processing_ms = result.ProcessingMs,
            note = "Original versus AI-returned image, not an independent identity reference. Score is not a probability or percentage. Experimental protection is not approved."
        };
        File.WriteAllText(Path.Combine(folder, "comparison.json"), JsonSerializer.Serialize(receipt, new JsonSerializerOptions { WriteIndented = true }));
        var panelWidth = Math.Max(300, input.Width);
        using var stack = new Bitmap(panelWidth * 3, input.Height + 130);
        using var graphics = Graphics.FromImage(stack);
        graphics.Clear(Color.White);
        using var title = new Font("맑은 고딕", 13, FontStyle.Bold);
        using var body = new Font("맑은 고딕", 10);
        using var scoreFont = new Font("Segoe UI", 32, FontStyle.Bold);
        graphics.DrawString("센서 원본", title, Brushes.Black, 12, 12);
        graphics.DrawString("서버 AI 처리본", title, Brushes.Black, panelWidth + 12, 12);
        graphics.DrawString("처리 전 ↔ 후 유사도", title, Brushes.Black, panelWidth * 2 + 12, 12);
        using var original = input.Preview();
        using var stream = new MemoryStream(result.Png);
        using var processed = Image.FromStream(stream);
        graphics.DrawImageUnscaled(original, (panelWidth - input.Width) / 2, 55);
        graphics.DrawImageUnscaled(processed, panelWidth + (panelWidth - input.Width) / 2, 55);
        graphics.DrawString(result.Score100Text, scoreFont, Brushes.DarkSlateBlue, panelWidth * 2 + 12, 90);
        graphics.DrawString("100점 환산 지수\n원시 점수: " + result.ScoreText + "\nSourceAFIS " + (result.EngineVersion ?? "미준비")
            + "\n환산: 100 × s / (s + 40)\n확률·인식률 아님\n" + result.StatusText,
            body, Brushes.Black, new RectangleF(panelWidth * 2 + 12, 160, panelWidth - 24, Math.Max(200, input.Height - 100)));
        graphics.DrawString(input.Synthetic ? "합성 자료 · 실제 센서 성능 시험 아님" : "실험 처리 결과 · 전체 지문 보호를 보장하지 않음",
            body, Brushes.DimGray, 12, input.Height + 70);
        stack.Save(Path.Combine(folder, "hstack.png"), ImageFormat.Png);
        return folder;
    }
}
