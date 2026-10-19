param(
    [Parameter(Mandatory=$true)][string]$PythonPath,
    [Parameter(Mandatory=$true)][string]$RosterPath,
    [Parameter(Mandatory=$true)][string]$StatePath,
    [switch]$NoBrowser
)
$ErrorActionPreference = 'Stop'
$aiRoot = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$scriptPath = Join-Path $aiRoot 'scripts/photo_visibility_annotation_v1.py'
foreach ($requiredPath in @($PythonPath,$RosterPath,$scriptPath)) {
    if (-not (Test-Path -LiteralPath $requiredPath -PathType Leaf)) { throw "Missing required file: $requiredPath" }
}
$PythonPath = (Resolve-Path -LiteralPath $PythonPath).Path
$RosterPath = (Resolve-Path -LiteralPath $RosterPath).Path
$StatePath = [System.IO.Path]::GetFullPath($StatePath)
$sessionPath = Join-Path $StatePath 'session.private.json'
$rosterHash = (Get-FileHash -LiteralPath $RosterPath -Algorithm SHA256).Hash.ToLowerInvariant()
$scriptHash = (Get-FileHash -LiteralPath $scriptPath -Algorithm SHA256).Hash.ToLowerInvariant()
function Get-VisibilitySession {
    if (-not (Test-Path -LiteralPath $sessionPath)) { return $null }
    try {
        $session = Get-Content -LiteralPath $sessionPath -Raw -Encoding UTF8 | ConvertFrom-Json
        if ($session.version -ne 'photo_visibility_annotation_v1' -or $session.roster_sha256 -ne $rosterHash) { return $null }
        if ($session.url -notmatch '^http://127\.0\.0\.1:[0-9]+/s/[A-Za-z0-9_-]+/$') { return $null }
        $serverProcess = Get-Process -Id $session.pid -ErrorAction SilentlyContinue
        if (-not $serverProcess) { return $null }
        $overview = Invoke-RestMethod -Uri ($session.url + 'api/project') -TimeoutSec 5
        if ($overview.version -ne $session.version -or $overview.roster_sha256 -ne $rosterHash) { return $null }
        if ($session.script_sha256 -ne $scriptHash) {
            $origin = ([uri]$session.url).GetLeftPart([System.UriPartial]::Authority)
            Invoke-RestMethod -Uri ($session.url + 'api/stop') -Method Post -ContentType 'application/json' -Headers @{Origin=$origin} -Body '{}' -TimeoutSec 5 | Out-Null
            $serverProcess.WaitForExit(5000) | Out-Null
            if (-not $serverProcess.HasExited) { throw 'Previous visibility server has not stopped.' }
            return $null
        }
        return $session
    } catch { return $null }
}
$session = Get-VisibilitySession
if (-not $session) {
    New-Item -ItemType Directory -Path $StatePath -Force | Out-Null
    $arguments = @('"' + $scriptPath + '"','--roster','"' + $RosterPath + '"','--state','"' + $StatePath + '"')
    $process = Start-Process -FilePath $PythonPath -ArgumentList ($arguments -join ' ') -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $StatePath 'server.stdout.log') -RedirectStandardError (Join-Path $StatePath 'server.stderr.log')
    $deadline = (Get-Date).AddSeconds(120)
    do {
        Start-Sleep -Milliseconds 500
        $session = Get-VisibilitySession
        if (-not $session -and $process.HasExited) { throw ('Visibility server failed. See: ' + (Join-Path $StatePath 'server.stderr.log')) }
    } while (-not $session -and (Get-Date) -lt $deadline)
    if (-not $session) { throw ('Startup timed out; check the existing process before retrying. Log: ' + (Join-Path $StatePath 'server.stderr.log')) }
}
if (-not $NoBrowser) { Start-Process $session.url }
Write-Output $session.url
