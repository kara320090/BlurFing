param(
    [Parameter(Mandatory=$true)][string]$PythonPath,
    [Parameter(Mandatory=$true)][string]$RosterPath,
    [Parameter(Mandatory=$true)][string]$StatePath,
    [Parameter(Mandatory=$true)][string]$OutputPath,
    [string[]]$SourceId = @()
)
$ErrorActionPreference = 'Stop'
$aiRoot = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$scriptPath = Join-Path $aiRoot 'scripts/photo_visibility_reviewed_batch_v1.py'
foreach ($requiredPath in @($PythonPath,$RosterPath,$scriptPath,(Join-Path $StatePath 'project.json'))) {
    if (-not (Test-Path -LiteralPath $requiredPath -PathType Leaf)) { throw "Missing required file: $requiredPath" }
}
if (Test-Path -LiteralPath $OutputPath) { throw 'A new output folder is required.' }
$arguments = @($scriptPath,'--roster',$RosterPath,'--state',$StatePath,'--output',$OutputPath)
foreach ($id in $SourceId) { $arguments += @('--source-id',$id) }
Write-Host 'Apply unchanged V19 only to human-reviewed visible whole pads. Uncertain regions remain original.'
$response = & $PythonPath @arguments
$code = $LASTEXITCODE
try { $result = ($response -join "`n") | ConvertFrom-Json } catch { throw 'Invalid reviewed batch response. See the error log above.' }
if ($code -ne 0 -or $result.status -eq 'error') { throw $result.reason }
Write-Output $result
