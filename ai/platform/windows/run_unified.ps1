param(
    [string]$CorePython = "",
    [string]$ColfispoofPython = $env:BLURFING_COLFISPOOF_PYTHON,
    [string]$ColfispoofSource = $env:BLURFING_COLFISPOOF_SOURCE,
    [string]$ColfispoofModel = $env:BLURFING_COLFISPOOF_MODEL,
    [string]$InputImage = "",
    [string]$OutputDirectory = "",
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
if ($Gui) {
    & $CorePython (Join-Path $aiRoot 'app\windows\unified_gui.py')
} else {
    if (-not $InputImage -or -not $OutputDirectory) { throw 'CLI requires InputImage and a fresh OutputDirectory' }
    & $CorePython (Join-Path $aiRoot 'scripts\protect_fingerprint.py') --input $InputImage --output $OutputDirectory
}
exit $LASTEXITCODE
