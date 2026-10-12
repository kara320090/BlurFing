param(
    [Parameter(Mandatory=$true)][string]$NbisSource,
    [Parameter(Mandatory=$true)][string]$BuildDir,
    [string]$Bash = 'bash',
    [string]$Compiler = 'g++'
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
function Invoke-NativeLogged {
    param([string]$FilePath, [string[]]$Arguments, [string]$LogPath)
    # Windows PowerShell 5.1 wraps redirected native stderr as ErrorRecord.
    # Keep diagnostics as log text and judge success by the process exit code.
    # This preference is function-local; file/log errors still terminate.
    $ErrorActionPreference = 'Continue'
    if (Get-Variable PSNativeCommandUseErrorActionPreference -ErrorAction SilentlyContinue) {
        $PSNativeCommandUseErrorActionPreference = $false
    }
    & $FilePath @Arguments 2>&1 |
        ForEach-Object { $_.ToString() } |
        Tee-Object -FilePath $LogPath -ErrorAction Stop
    $NativeExitCode = $LASTEXITCODE
    if ($NativeExitCode -ne 0) {
        throw "Native command failed: $FilePath exit=$NativeExitCode; log=$LogPath"
    }
}
if ([Environment]::OSVersion.Platform -ne 'Win32NT') { throw 'Run under Windows with a compatible MinGW-w64/MSYS environment.' }
foreach ($tool in @($Bash, $Compiler)) {
    if (-not (Get-Command $tool -ErrorAction SilentlyContinue)) { throw "Missing build prerequisite: $tool" }
}
$NbisSource = (Resolve-Path -LiteralPath $NbisSource).Path
if (-not (Test-Path (Join-Path $NbisSource 'setup.sh'))) { throw 'NbisSource must point to official Rel_5.0.0.' }
$BuildDir = [IO.Path]::GetFullPath($BuildDir)
if (Test-Path -LiteralPath $BuildDir) { throw 'BuildDir must be new; refusing to overwrite.' }
# Official NBIS Makefiles require a simple path. Reject unsupported names rather than guessing quotes.
$BuildSlash = $BuildDir.Replace([char]92, [char]47)
if ($BuildSlash -notmatch '^[A-Za-z]:/[A-Za-z0-9_/.-]+$') { throw 'Use a new absolute ASCII drive path with no spaces.' }
New-Item -ItemType Directory -Path $BuildDir | Out-Null
$Tree = Join-Path $BuildDir 'Rel_5.0.0'
Copy-Item -LiteralPath $NbisSource -Destination $Tree -Recurse
$Install = Join-Path $BuildDir 'install'
New-Item -ItemType Directory -Path $Install | Out-Null
$TreeUnix = $Tree.Replace([char]92, [char]47)
$InstallUnix = $Install.Replace([char]92, [char]47)
$BuildCommand = @"
set -eu
# Legacy PNG/zlib export targets lack parallel prerequisites. Build serially.
export MAKEFLAGS=-j1
cd '$TreeUnix'
command -v gcc
command -v g++
command -v make
./setup.sh '$InstallUnix' --MSYS --64
make config
# --MSYS enables PNG and OpenJPEG; their headers/libs are required by imgtools.
for pkg in ijg png openjp2 pcasys commonnbis imgtools an2k mindtct bozorth3; do make -C "`$pkg" cpheaders; done
for pkg in ijg png openjp2 commonnbis imgtools an2k mindtct bozorth3; do make -C "`$pkg" libs; done
make -C mindtct bins
make -C bozorth3 bins
make -C imgtools/src/bin/dwsq
"@
Invoke-NativeLogged -FilePath $Bash -Arguments @('--login', '-c', $BuildCommand) -LogPath (Join-Path $BuildDir 'nbis_build.log')
$Include = Join-Path $Tree 'exports/include'
$LibDir = Join-Path $Tree 'exports/lib'
$Names = @('mindtct','bozorth3','an2k','image','ihead','wsq','jpegl','jpegb','fet','cblas','ioutil','util','openjp2','png','z')
$Libraries = @()
foreach ($name in $Names) {
    $lib = Join-Path $LibDir ("lib$name.a")
    if (-not (Test-Path -LiteralPath $lib)) { throw "Missing NBIS library: $name" }
    $Libraries += $lib
}
$Exe = Join-Path $BuildDir 'nbis_local_windows.exe'
$Bridge = Join-Path $PSScriptRoot 'nbis_local_windows.cpp'
$ArgsList = @('-std=c++17','-O2','-Wall','-Wextra','-municode',"-I$Include",$Bridge,'-Wl,--start-group') + $Libraries + @('-Wl,--end-group','-lm','-o',$Exe)
Invoke-NativeLogged -FilePath $Compiler -Arguments $ArgsList -LogPath (Join-Path $BuildDir 'bridge_build.log')
$Hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $Exe).Hash.ToLowerInvariant()
$Runtime = @{ version='NBIS5.0.0'; contract='blurfing-raw-match-v1'; exe=$Exe; exe_sha256=$Hash }
# UTF-8 without BOM is compatible with the adapter JSON reader in Windows PowerShell 5.1 and 7.
$Config = Join-Path $BuildDir 'nbis_windows.runtime.json'
[IO.File]::WriteAllText($Config, ($Runtime | ConvertTo-Json), (New-Object Text.UTF8Encoding($false)))
Write-Host "Build artifact produced: $Exe"
Write-Host "SHA-256: $Hash"
Write-Host "Runtime config: $Config"
Write-Host 'Build success is not Windows runtime validation. Check DLL dependencies and run the fixture validator.'
