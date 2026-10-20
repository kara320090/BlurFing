using System.Runtime.CompilerServices;

[assembly: InternalsVisibleTo("BlurFing.ScannerComparison.Checks")]

namespace BlurFing.ScannerComparison;

internal static class Program
{
    [STAThread]
    private static void Main(string[] args)
    {
        ApplicationConfiguration.Initialize();
        Application.Run(new ComparisonForm(args.Contains("--preview")));
    }
}
