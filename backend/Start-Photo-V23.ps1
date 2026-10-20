param(
    [Parameter(Mandatory=$true)][string]$ServerPython,
    [Parameter(Mandatory=$true)][string]$AiPython,
    [Parameter(Mandatory=$true)][string]$ModelPath,
    [Parameter(Mandatory=$true)][string]$RegistryPath,
    [ValidateRange(1024,65535)][int]$Port=8001,
    [switch]$DevelopmentReplay
)
$ErrorActionPreference='Stop'
foreach($file in @($ServerPython,$AiPython,$RegistryPath,(Join-Path $ModelPath 'final_config.private.json'),(Join-Path $ModelPath 'final_context_whole_pad.pt'))) {
    if(!(Test-Path -LiteralPath $file -PathType Leaf)){throw "Required runtime file is missing: $file"}
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
& $ServerPython -m uvicorn experimental_photo_main:app --app-dir $PSScriptRoot --host 127.0.0.1 --port $Port
exit $LASTEXITCODE
