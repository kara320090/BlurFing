param(
    [string]$NbisConfig = $env:BLURFING_NBIS_CONFIG,
    [string]$SourceAfisHome = $env:BLURFING_SOURCEAFIS_HOME
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
if ([Environment]::OSVersion.Platform -ne 'Win32NT') { throw 'Run on Windows.' }
Write-Host ([Environment]::OSVersion.VersionString)
foreach ($tool in @('python', 'java', 'javac')) {
    if (-not (Get-Command $tool -ErrorAction SilentlyContinue)) { throw "Missing prerequisite: $tool" }
}
& python -c 'import sys; assert sys.version_info >= (3,10), "Python >=3.10 required"; print(sys.version)'
if ($LASTEXITCODE -ne 0) { throw 'Python version check failed.' }
& python -m pip --version
if ($LASTEXITCODE -ne 0) { throw 'pip unavailable.' }
& java -version
if ($LASTEXITCODE -ne 0) { throw 'Java check failed.' }
& javac -version
if ($LASTEXITCODE -ne 0) { throw 'javac check failed.' }
if ($NbisConfig) { $env:BLURFING_NBIS_CONFIG = (Resolve-Path -LiteralPath $NbisConfig).Path }
if ($SourceAfisHome) { $env:BLURFING_SOURCEAFIS_HOME = (Resolve-Path -LiteralPath $SourceAfisHome).Path }
$AiRoot = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
Write-Host 'Install requirements inside your venv: python -m pip install -r ai/requirements.txt'
& python (Join-Path $AiRoot 'scripts/check_platform_runtime.py') --require-all
if ($LASTEXITCODE -ne 0) { throw 'Runtime prerequisites missing: inspect report above. No evaluation was run.' }
