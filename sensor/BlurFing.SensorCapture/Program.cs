namespace BlurFing.SensorCapture;

internal static class Program
{
    [STAThread]
    private static int Main(string[] args)
    {
        if (args.Length > 0 && args[0] == "--worker")
            return CaptureWorker.Run(args);
        ApplicationConfiguration.Initialize();
        Application.Run(new MainForm());
        return 0;
    }
}
