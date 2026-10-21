// Copyright (C) 2026 Lee Bongheon / BlurFing.
// Reuses the locally verified SensorPreview UFS adapter (2026-10-16).
using System;
using System.IO;
using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Threading;
    internal sealed class NativeScanner
    {
        [DllImport("kernel32.dll", CharSet = CharSet.Unicode, EntryPoint = "LoadLibraryExW", SetLastError = true)]
        private static extern IntPtr LoadLibraryEx(string path, IntPtr reserved, uint flags);
        [DllImport("kernel32.dll", CharSet = CharSet.Ansi, SetLastError = true)]
        private static extern IntPtr GetProcAddress(IntPtr library, string name);
        [DllImport("kernel32.dll", CharSet = CharSet.Unicode, EntryPoint = "SetDllDirectoryW", SetLastError = true)]
        private static extern bool SetDllDirectory(string path);
        [UnmanagedFunctionPointer(CallingConvention.StdCall)] private delegate int NoArguments();
        [UnmanagedFunctionPointer(CallingConvention.StdCall)] private delegate int CountFunction(out int count);
        [UnmanagedFunctionPointer(CallingConvention.StdCall)] private delegate int HandleFunction(int index, out IntPtr handle);
        [UnmanagedFunctionPointer(CallingConvention.StdCall)] private delegate int HandleCall(IntPtr handle);
        [UnmanagedFunctionPointer(CallingConvention.StdCall)] private delegate int CaptureStatus(IntPtr handle, out int active);
        [UnmanagedFunctionPointer(CallingConvention.StdCall)] public delegate int FrameCallback(IntPtr handle, int finger, IntPtr pixels, int width, int height, int resolution, IntPtr parameter);
        [UnmanagedFunctionPointer(CallingConvention.StdCall)] private delegate int StartFunction(IntPtr handle, FrameCallback callback, IntPtr parameter);
        [UnmanagedFunctionPointer(CallingConvention.StdCall)] private delegate int ParameterFunction(IntPtr handle, int parameter, ref int value);
        private readonly IntPtr library;
        private IntPtr scanner;
        private bool initialized;
        private FrameCallback callback;
        private int? previousTimeout;
        private readonly Action<string, string> log;
        public int ScannerCount { get; private set; }

        public NativeScanner(string path, Action<string, string> log)
        {
            this.log = log;
            path = Path.GetFullPath(path);
            if (!File.Exists(path)) throw new FileNotFoundException("UFScanner.dll을 찾을 수 없습니다.", path);
            // UFScanner also loads tensorflowlite_c.dll dynamically during UFS_Init.
            // Its own directory must stay in the DLL search path for that operation.
            if (!SetDllDirectory(Path.GetDirectoryName(path))) throw new System.ComponentModel.Win32Exception(Marshal.GetLastWin32Error());
            library = LoadLibraryEx(path, IntPtr.Zero, 8);
            if (library == IntPtr.Zero) throw new System.ComponentModel.Win32Exception(Marshal.GetLastWin32Error());
            // The SDK library remains loaded for this process lifetime so callback
            // code is never unloaded while a native thread could still use it.
        }
        private T Function<T>(string name) where T : class
        {
            IntPtr address = GetProcAddress(library, name);
            if (address == IntPtr.Zero) throw new EntryPointNotFoundException(name);
            return (T)(object)Marshal.GetDelegateForFunctionPointer(address, typeof(T));
        }
        private void Check(string name, int code)
        {
            log("SDK_CALL", name + "=" + code);
            if (code != 0) throw new InvalidOperationException(name + " 실패: SDK 코드 " + code);
        }
        public void Open()
        {
            Check("UFS_Init", Function<NoArguments>("UFS_Init")()); initialized = true;
            int count; Check("UFS_GetScannerNumber", Function<CountFunction>("UFS_GetScannerNumber")(out count));
            ScannerCount = count;
            if (count < 1) throw new InvalidOperationException("연결된 센서가 없습니다.");
            Check("UFS_GetScannerHandle", Function<HandleFunction>("UFS_GetScannerHandle")(0, out scanner));
            if (scanner == IntPtr.Zero) throw new InvalidDataException("SDK가 빈 장치 핸들을 반환했습니다.");
        }
        public void Start(FrameCallback receiver)
        {
            callback = receiver;
            Check("UFS_StartCapturing", Function<StartFunction>("UFS_StartCapturing")(scanner, callback, IntPtr.Zero));
        }
        public void ConfigureTimeout(int milliseconds)
        {
            // UFS_PARAM_TIMEOUT=201 is documented as an int in milliseconds.
            int original = 0;
            Check("UFS_GetParameter(TIMEOUT)", Function<ParameterFunction>("UFS_GetParameter")(scanner, 201, ref original));
            previousTimeout = original;
            Check("UFS_SetParameter(TIMEOUT)", Function<ParameterFunction>("UFS_SetParameter")(scanner, 201, ref milliseconds));
            int applied = 0;
            Check("UFS_GetParameter(TIMEOUT readback)", Function<ParameterFunction>("UFS_GetParameter")(scanner, 201, ref applied));
            log("CAPTURE_TIMEOUT", "AppliedMs=" + applied);
            if (applied != milliseconds) throw new InvalidOperationException("SDK 취득 제한 시간 적용값이 일치하지 않습니다.");
        }
        public bool IsCapturing()
        {
            int active; int code = Function<CaptureStatus>("UFS_IsCapturing")(scanner, out active);
            if (code != 0) Check("UFS_IsCapturing", code);
            return active != 0;
        }
        public void Stop()
        {
            Check("UFS_AbortCapturing", Function<HandleCall>("UFS_AbortCapturing")(scanner));
            Stopwatch clock = Stopwatch.StartNew();
            while (IsCapturing())
            {
                if (clock.ElapsedMilliseconds > 5000) throw new TimeoutException("SDK 취득 중단 후에도 동작 중입니다. 이 세션에서는 엔진을 해제하지 않습니다.");
                Thread.Sleep(50);
            }
            GC.KeepAlive(callback);
        }
        public void Close()
        {
            if (initialized)
            {
                if (previousTimeout.HasValue)
                {
                    int original = previousTimeout.Value;
                    Check("UFS_SetParameter(TIMEOUT restore)", Function<ParameterFunction>("UFS_SetParameter")(scanner, 201, ref original));
                }
                Check("UFS_Uninit", Function<NoArguments>("UFS_Uninit")()); initialized = false;
            }
            GC.KeepAlive(callback);
        }
    }

