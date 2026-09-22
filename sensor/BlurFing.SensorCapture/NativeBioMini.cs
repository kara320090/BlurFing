using System.Reflection;
using System.Runtime.InteropServices;

namespace BlurFing.SensorCapture;

// Function signatures are based on Xperix's official sample linked in sensor/README.md.
// Confirm against the purchased SDK's header and test on hardware before research use.
internal sealed class NativeBioMini : IDisposable
{
    [UnmanagedFunctionPointer(CallingConvention.StdCall)] private delegate int InitFn();
    [UnmanagedFunctionPointer(CallingConvention.StdCall)] private delegate int CountFn(out int count);
    [UnmanagedFunctionPointer(CallingConvention.StdCall)] private delegate int HandleFn(int index, out IntPtr handle);
    [UnmanagedFunctionPointer(CallingConvention.StdCall)] private delegate int CaptureFn(IntPtr handle);
    [UnmanagedFunctionPointer(CallingConvention.StdCall, CharSet = CharSet.Ansi)]
    private delegate int SaveFn(IntPtr handle, [MarshalAs(UnmanagedType.LPStr)] string fileName);

    private IntPtr library;
    private bool initialized;
    private readonly InitFn uninit;
    private readonly CountFn getCount;
    private readonly HandleFn getHandle;
    private readonly CaptureFn capture;
    private readonly SaveFn save;

    public NativeBioMini(string dllPath)
    {
        if (!File.Exists(dllPath))
            throw new FileNotFoundException("SDK의 UFScanner.dll이 없습니다. 제조사 SDK를 먼저 설치하세요.");
        try
        {
            library = NativeLibrary.Load(Path.GetFullPath(dllPath), Assembly.GetExecutingAssembly(),
                DllImportSearchPath.UseDllDirectoryForDependencies | DllImportSearchPath.System32);
            var init = Function<InitFn>("UFS_Init");
            uninit = Function<InitFn>("UFS_Uninit");
            getCount = Function<CountFn>("UFS_GetScannerNumber");
            getHandle = Function<HandleFn>("UFS_GetScannerHandle");
            capture = Function<CaptureFn>("UFS_CaptureSingleImage");
            save = Function<SaveFn>("UFS_SaveCaptureImageBufferToBMP");
            Check(init(), "SDK 초기화");
            initialized = true;
        }
        catch
        {
            if (library != IntPtr.Zero) NativeLibrary.Free(library);
            library = IntPtr.Zero;
            throw;
        }
    }

    private T Function<T>(string name) where T : Delegate =>
        Marshal.GetDelegateForFunctionPointer<T>(NativeLibrary.GetExport(library, name));

    private static void Check(int result, string operation)
    {
        if (result != 0)
            throw new InvalidOperationException($"{operation} 실패 (SDK 코드 {result}). SDK 설명서에서 원인을 확인하세요.");
    }

    public int GetDeviceCount()
    {
        Check(getCount(out var count), "센서 수 조회");
        if (count < 0 || count > 100) throw new InvalidDataException("SDK가 잘못된 장치 수를 반환했습니다.");
        return count;
    }

    public void Capture(int deviceIndex)
    {
        var count = GetDeviceCount();
        if (deviceIndex < 0 || deviceIndex >= count)
            throw new InvalidOperationException("선택한 센서가 없습니다. USB 연결과 드라이버를 확인하세요.");
        Check(getHandle(deviceIndex, out var handle), "센서 선택");
        if (handle == IntPtr.Zero) throw new InvalidDataException("SDK가 빈 장치 핸들을 반환했습니다.");
        Check(capture(handle), "지문 한 장 취득");
        // Relative ASCII name avoids the SDK's unspecified non-ASCII path encoding.
        Check(save(handle, "capture.bmp"), "BMP 저장");
    }

    public void Dispose()
    {
        if (library == IntPtr.Zero) return;
        try { if (initialized) uninit(); }
        finally { NativeLibrary.Free(library); library = IntPtr.Zero; initialized = false; }
    }
}
