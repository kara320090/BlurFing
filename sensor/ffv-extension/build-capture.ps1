param(
    [string]$SdkRoot = (Join-Path $PSScriptRoot 'FreeFingerprintVerification_3_1_SDK'),
    [string]$OutputName = 'BlurFingFfvCapture.exe'
)

$ErrorActionPreference = 'Stop'
$sdkBin = Join-Path $SdkRoot 'Bin\Win64_x64'
$sourceFile = Join-Path $PSScriptRoot 'BlurFingFfvCapture.cs'
if ($OutputName -notmatch '^BlurFing[A-Za-z0-9_-]+\.exe$') { throw 'Use a simple BlurFing executable name.' }
$outputFile = Join-Path $sdkBin $OutputName
$bridgeFile = Join-Path $PSScriptRoot 'BlurFingComparisonBridge.cs'
$compiler = Join-Path $env:WINDIR 'Microsoft.NET\Framework64\v4.0.30319\csc.exe'
foreach ($requiredFile in @($compiler, $sourceFile, $bridgeFile, (Join-Path $sdkBin 'CSharpSample.exe'), (Join-Path $sdkBin 'Neurotec.Biometrics.Nffv.dll'))) {
    if (-not (Test-Path -LiteralPath $requiredFile -PathType Leaf)) {
        throw "Required file not found: $requiredFile. Check .NET Framework 4.8 and the complete official FFV SDK path."
    }
}
& $compiler /nologo /target:winexe /platform:x64 /optimize+ "/out:$outputFile" "/reference:$sdkBin\CSharpSample.exe" "/reference:$sdkBin\Neurotec.Biometrics.Nffv.dll" /reference:System.Windows.Forms.dll /reference:System.Drawing.dll /reference:System.Core.dll $sourceFile $bridgeFile
if ($LASTEXITCODE -ne 0) { throw 'C# compilation failed.' }
@'
<?xml version="1.0" encoding="utf-8" ?>
<configuration><startup><supportedRuntime version="v4.0" sku=".NETFramework,Version=v4.8" /></startup></configuration>
'@ | Set-Content -LiteralPath "$outputFile.config" -Encoding UTF8
Get-Item -LiteralPath $outputFile | Select-Object FullName,Length
