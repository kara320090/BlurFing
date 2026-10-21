using System.Reflection.Metadata;
using System.Reflection.PortableExecutable;

namespace BlurFing.ScannerComparison;

internal static class FfvHelperConfiguration
{
    internal static string? Problem(string? path)
    {
        if (string.IsNullOrWhiteSpace(path) || !File.Exists(path))
            return "FFV 취득기 파일을 찾지 못했습니다.";
        if (IsComparisonProgram(path))
            return "비교 프로그램을 취득기로 선택했습니다. 공식 FFV SDK의 Bin/Win64_x64에 있는 BlurFingFfvOneClick 취득기를 선택하세요.";
        try
        {
            // Inspect metadata without loading or executing the selected program.
            using var file = File.OpenRead(path);
            using var pe = new PEReader(file);
            if (!pe.HasMetadata) return "BlurFing FFV 원클릭 취득기 실행 파일이 아닙니다.";
            var metadata = pe.GetMetadataReader();
            if (!metadata.TypeDefinitions.Any(handle =>
            {
                var type = metadata.GetTypeDefinition(handle);
                return metadata.GetString(type.Name) == "BlurFingOneShot" && type.GetMethods().Any(method =>
                    metadata.GetString(metadata.GetMethodDefinition(method).Name) == "Run");
            })) return "새 지문 원클릭 취득 기능이 없는 파일입니다. BlurFingFfvOneClick 취득기를 선택하세요.";
            var directory = Path.GetDirectoryName(Path.GetFullPath(path))!;
            foreach (var dependency in new[] { "CSharpSample.exe", "Neurotec.Biometrics.Nffv.dll", "Nffv.dll", "NffvServer.exe" })
                if (!File.Exists(Path.Combine(directory, dependency)))
                    return "FFV SDK 종속 파일이 없습니다. 전달 폴더의 EXE만 선택하지 말고 전체 공식 SDK의 Bin/Win64_x64에 있는 취득기를 선택하세요.";
            if (!Directory.Exists(Path.Combine(directory, "FScanners")))
                return "FFV 스캐너 모듈 폴더가 없습니다. 전체 공식 SDK의 Bin/Win64_x64에 있는 취득기를 선택하세요.";
            return null;
        }
        catch (Exception error) when (error is IOException or UnauthorizedAccessException or BadImageFormatException)
        {
            return "FFV 취득기 파일을 확인하지 못했습니다. 전체 공식 SDK의 원클릭 취득기를 선택하세요.";
        }
    }

    internal static bool IsComparisonProgram(string path) =>
        string.Equals(Path.GetFileName(path), "BlurFing.ScannerComparison.exe", StringComparison.OrdinalIgnoreCase);

    // A valid personal choice still wins. Recover stale/incorrect choices only.
    internal static string? Resolve(string? saved, string? portable) =>
        Problem(saved) is null ? saved : Problem(portable) is null ? portable : null;
}
