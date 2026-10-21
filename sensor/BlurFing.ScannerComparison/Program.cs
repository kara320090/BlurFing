using System.Runtime.CompilerServices;

[assembly: InternalsVisibleTo("BlurFing.ScannerComparison.Checks")]

namespace BlurFing.ScannerComparison;

internal static class Program
{
    [STAThread]
    private static void Main(string[] args)
    {
        // Never recursively open this UI if an older client chooses us as helper.
        if (args.Contains("--capture-once")) return;
        ApplicationConfiguration.Initialize();
        if (args.Length == 2 && args[0] is "--render-preview" or "--render-empty-preview" or "--render-compact-preview" or "--render-tools-preview")
        {
            using var preview = new ComparisonForm();
            if (args[0] == "--render-compact-preview") preview.ClientSize = new Size(1080, 770);
            preview.RenderDesignPreview(args[1], args[0] == "--render-preview", args[0] == "--render-tools-preview"); return;
        }
        Application.Run(new ComparisonForm(args.Contains("--preview")));
    }
}
