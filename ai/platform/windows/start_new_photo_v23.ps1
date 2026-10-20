param(
    [Parameter(Mandatory=$true)][string]$PythonPath,
    [Parameter(Mandatory=$true)][string]$OutputRoot,
    [string]$ModelPath='',
    [string]$RegistryPath='',
    [switch]$NoOpen
)
$ErrorActionPreference='Stop'
$aiRoot=Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$scriptPath=Join-Path $aiRoot 'scripts/photo_new_input_v23.py'
foreach ($required in @($PythonPath,$scriptPath)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) { throw "Missing file: $required" }
}
$basePath=[System.IO.Path]::GetFullPath($OutputRoot)
[void][System.IO.Directory]::CreateDirectory($basePath)
$sessionName=(Get-Date -Format 'yyyyMMdd_HHmmss')+'_'+([guid]::NewGuid().ToString('N').Substring(0,8))
$sessionPath=Join-Path $basePath $sessionName
$readyPath=Join-Path $basePath ($sessionName+'.ready.private.json')
$logPath=Join-Path $basePath ($sessionName+'.log')
$errorPath=Join-Path $basePath ($sessionName+'.error.log')
$arguments=@($scriptPath,'--output',$sessionPath,'--ready-file',$readyPath)
if ($ModelPath -and $RegistryPath) { $arguments+=@('--model',$ModelPath,'--registry',$RegistryPath) }
# Process arguments are literal quoted paths, not another shell command.
$quotedArguments=($arguments | ForEach-Object {
    if ($_.Contains('"')) { throw 'Double quote is not allowed in an argument.' }
    '"'+$_+'"'
}) -join ' '
$env:PYTHONUTF8='1'
$process=Start-Process -FilePath $PythonPath -ArgumentList $quotedArguments -WindowStyle Hidden -PassThru `
    -RedirectStandardOutput $logPath -RedirectStandardError $errorPath
$deadline=(Get-Date).AddSeconds(30)
while (-not (Test-Path -LiteralPath $readyPath)) {
    $process.Refresh()
    if ($process.HasExited) { throw "New photo UI failed to start. See $errorPath" }
    if ((Get-Date) -gt $deadline) { throw "Startup still pending. Check $readyPath and $errorPath" }
    Start-Sleep -Milliseconds 250
}
$ready=Get-Content -LiteralPath $readyPath -Raw -Encoding UTF8 | ConvertFrom-Json
Write-Host ('New photo UI: '+$ready.url)
Write-Host ('Results: '+$ready.output)
Write-Host 'Close the server with the Exit button in the page. Originals and old results are preserved.'
if (-not $NoOpen) { Start-Process -FilePath $ready.url }
Write-Output $ready
