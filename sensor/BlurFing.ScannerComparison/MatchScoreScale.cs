using System.Globalization;

namespace BlurFing.ScannerComparison;

// Display scale only. This does not calibrate an identity probability or make
// a match decision. The raw SourceAFIS score is retained without a 100 cap.
internal static class MatchScoreScale
{
    public const string Method = "sourceafis-display-100-v1";
    public const double Reference = 40;
    public const string Formula = "100 * raw_score / (raw_score + 40)";
    public const string EmptyExplanation = "처리 전 ↔ 후 유사도를\n100점 환산 지수로 표시합니다.\n\n높을수록 두 영상이 유사합니다.\n확률·인식률이 아닙니다.";

    public static double? Convert(double? raw) => raw is { } value && double.IsFinite(value) && value >= 0
        ? 100 * (value / (value + Reference)) : null;

    public static string Format(double? raw) => Convert(raw) is { } value
        ? value.ToString("0.0", CultureInfo.InvariantCulture) : "미측정";
}
