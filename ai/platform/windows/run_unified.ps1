param(
    [string]$CorePython = "",
    [string]$ColfispoofPython = $env:BLURFING_COLFISPOOF_PYTHON,
    [string]$ColfispoofSource = $env:BLURFING_COLFISPOOF_SOURCE,
    [string]$ColfispoofModel = $env:BLURFING_COLFISPOOF_MODEL,
    [string]$InputImage = "",
    [string]$OutputDirectory = "",
    [ValidateSet('legacy','native_v12','distal_v13','pose_v14')][string]$PhotoEngine = 'legacy',
    [string]$PhotoModel = "",
    [string]$ConsumedRegistry = "",
    [switch]$DevelopmentReplay,
    [switch]$Gui
)
$ErrorActionPreference = 'Stop'
$aiRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
if (-not $CorePython) { $CorePython = Join-Path $aiRoot '.venv\Scripts\python.exe' }
if (-not (Test-Path -LiteralPath $CorePython -PathType Leaf)) { throw 'Configured core Python is missing' }
$env:BLURFING_CORE_PYTHON = $CorePython
$env:PYTHONUTF8 = '1'
$workerValues = @($ColfispoofPython, $ColfispoofSource, $ColfispoofModel)
if (@($workerValues | Where-Object { $_ }).Count -gt 0) {
    if (@($workerValues | Where-Object { $_ }).Count -ne 3) { throw 'Supply all three COLFISPOOF runtime paths' }
    foreach ($workerPath in $workerValues) {
        if (-not (Test-Path -LiteralPath $workerPath)) { throw 'A configured COLFISPOOF runtime path is missing' }
    }
    $env:BLURFING_COLFISPOOF_PYTHON = $ColfispoofPython
    $env:BLURFING_COLFISPOOF_SOURCE = $ColfispoofSource
    $env:BLURFING_COLFISPOOF_MODEL = $ColfispoofModel
}
$photoArguments = @()
if ($PhotoEngine -eq 'legacy') {
    if ($PhotoModel -or $ConsumedRegistry -or $DevelopmentReplay) { throw 'Experimental PHOTO options require an explicit native_v12, distal_v13 or pose_v14 engine' }
} else {
    if (-not $ConsumedRegistry -or -not (Test-Path -LiteralPath $ConsumedRegistry -PathType Leaf)) { throw 'Experimental PHOTO engine requires a private consumed registry JSON' }
    $photoArguments = @('--photo-engine',$PhotoEngine,'--consumed-registry',$ConsumedRegistry)
    if ($PhotoEngine -eq 'native_v12') {
        if (-not $PhotoModel -or -not (Test-Path -LiteralPath $PhotoModel -PathType Container)) { throw 'native_v12 requires a completed private V6 model folder' }
        $photoArguments += @('--photo-model',$PhotoModel)
    } elseif ($PhotoModel) { throw 'Geometry PHOTO engines use no learned pad model; do not supply PhotoModel' }
    if ($DevelopmentReplay) { $photoArguments += '--development-replay' }
}
if ($Gui) {
    & $CorePython (Join-Path $aiRoot 'app\windows\unified_gui.py') @photoArguments
} else {
    if (-not $InputImage -or -not $OutputDirectory) { throw 'CLI requires InputImage and a fresh OutputDirectory' }
    & $CorePython (Join-Path $aiRoot 'scripts\protect_fingerprint.py') --input $InputImage --output $OutputDirectory @photoArguments
}
exit $LASTEXITCODE
