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
        Application.Run(new ComparisonForm(args.Contains("--preview")));
    }
}
