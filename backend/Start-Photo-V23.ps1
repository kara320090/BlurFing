param(
    [Parameter(Mandatory=$true)][string]$ServerPython,
    [Parameter(Mandatory=$true)][string]$AiPython,
    [Parameter(Mandatory=$true)][string]$ModelPath,
    [Parameter(Mandatory=$true)][string]$RegistryPath,
    [ValidateRange(1024,65535)][int]$Port=8001,
    [switch]$DevelopmentReplay,
    [switch]$ReuseRunning
)
$ErrorActionPreference='Stop'
foreach($file in @($ServerPython,$AiPython,$RegistryPath,(Join-Path $ModelPath 'final_config.private.json'),(Join-Path $ModelPath 'final_context_whole_pad.pt'))) {
    if(!(Test-Path -LiteralPath $file -PathType Leaf)){throw "Required runtime file is missing: $file"}
}
$listeners=@(Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue)
if($listeners.Count -gt 0) {
    if(!$ReuseRunning) {
        throw "Port $Port is already in use. Choose another -Port, or use -ReuseRunning for an existing V23 server."
    }
    # A matching /ready response alone does not prove this is our server.
    $backendPattern='--app-dir\s+"?'+[regex]::Escape($PSScriptRoot)+'"?(?:\s|$)'
    foreach($listener in $listeners) {
        $ownerProcess=Get-CimInstance Win32_Process -Filter ("ProcessId="+$listener.OwningProcess)
        if($listener.LocalAddress -ne '127.0.0.1' -or
           !$ownerProcess -or
           $ownerProcess.CommandLine -notmatch '-m\s+uvicorn\s+experimental_photo_main:app(?:\s|$)' -or
           $ownerProcess.CommandLine -notmatch $backendPattern) {
            throw "Port $Port belongs to another application. It was not stopped. Choose another -Port."
        }
    }
    try {
        $ready=Invoke-RestMethod -Uri "http://127.0.0.1:$Port/ready" -TimeoutSec 5
    } catch {
        throw "The existing server on port $Port is not ready. No second server was started."
    }
    if($ready.status -ne 'ready' -or $ready.contract_version -ne 'photo-experimental-v2' -or
       $ready.result_kind -ne 'experimental' -or $ready.production_approved -ne $false -or
       @($ready.photo_engines).Count -ne 1 -or $ready.photo_engines[0] -ne 'synthetic_v23') {
        throw "Port $Port is not a ready V23-only server. No second server was started."
    }
    Write-Host 'V23 server is already running. Reusing its EXISTING configuration.'
    Write-Host "PC status: http://127.0.0.1:$Port/ready (JSON status, not a photo-upload page)."
    Write-Host "Android emulator server address: http://10.0.2.2:$Port"
    Write-Host 'No new server was started; closing this status window will not stop the existing server.'
    exit 0
}
$env:BLURFING_PHOTO_PYTHON=(Resolve-Path -LiteralPath $AiPython).Path
$env:BLURFING_PHOTO_BRIDGE=Join-Path (Split-Path $PSScriptRoot -Parent) 'ai/scripts/export_photo_permissions_v1.py'
$env:BLURFING_PHOTO_MODEL=(Resolve-Path -LiteralPath $ModelPath).Path
$env:BLURFING_PHOTO_CONSUMED_REGISTRY=(Resolve-Path -LiteralPath $RegistryPath).Path
$env:BLURFING_PHOTO_ENGINES='synthetic_v23'
$env:BLURFING_PHOTO_DEVELOPMENT_REPLAY=if($DevelopmentReplay){'true'}else{'false'}
$env:BLURFING_PHOTO_TIMEOUT_SECONDS='600'
Write-Host 'V23 automatic experiment. Uncertain regions may retain original fingerprints.'
Write-Host "Emulator URL: http://10.0.2.2:$Port . USB device: adb reverse tcp:$Port tcp:$Port"
Write-Host "PC status: http://127.0.0.1:$Port/ready (JSON status, not a photo-upload page)."
Write-Host 'Leave this window open while using the app. Press Ctrl+C to stop this server.'
& $ServerPython -m uvicorn experimental_photo_main:app --app-dir $PSScriptRoot --host 127.0.0.1 --port $Port
exit $LASTEXITCODE
