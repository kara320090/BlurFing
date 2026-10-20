param(
    [Parameter(Mandatory=$true)][string]$PythonPath,
    [Parameter(Mandatory=$true)][string]$RosterPath,
    [Parameter(Mandatory=$true)][string]$StatePath,
    [Parameter(Mandatory=$true)][string]$OutputRoot,
    [string[]]$SourceId = @(),
    [string]$Seed = '',
    [switch]$NoOpen
)
$ErrorActionPreference = 'Stop'
$aiRoot = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$scriptPath = Join-Path $aiRoot 'scripts/photo_reviewed_demo_v23.py'
foreach ($requiredPath in @($PythonPath,$RosterPath,$scriptPath,(Join-Path $StatePath 'project.json'))) {
    if (-not (Test-Path -LiteralPath $requiredPath -PathType Leaf)) { throw "Missing required file: $requiredPath" }
}
if (-not $SourceId.Count) {
    Add-Type -AssemblyName System.Windows.Forms
    $roster = Get-Content -LiteralPath $RosterPath -Raw -Encoding UTF8 | ConvertFrom-Json
    $form = New-Object System.Windows.Forms.Form
    $form.Text = 'BlurFing V23 - select reviewed photos'
    $form.Width = 600
    $form.Height = 480
    $form.StartPosition = 'CenterScreen'
    $list = New-Object System.Windows.Forms.ListBox
    $list.Dock = 'Fill'
    $list.SelectionMode = 'MultiExtended'
    foreach ($item in $roster.sources) { [void]$list.Items.Add([string]$item.source_id) }
    $note = New-Object System.Windows.Forms.Label
    $note.Text = 'Select photo IDs (Ctrl/Shift for multiple). Only completed human reviews can run.'
    $note.Dock = 'Top'
    $note.Height = 40
    $button = New-Object System.Windows.Forms.Button
    $button.Text = 'Run V23'
    $button.Dock = 'Bottom'
    $button.Height = 42
    $button.DialogResult = [System.Windows.Forms.DialogResult]::OK
    $form.Controls.Add($list)
    $form.Controls.Add($note)
    $form.Controls.Add($button)
    $form.AcceptButton = $button
    try {
        $dialogResult = $form.ShowDialog()
        if ($dialogResult -ne [System.Windows.Forms.DialogResult]::OK -or -not $list.SelectedItems.Count) {
            Write-Output 'Cancelled. No output created.'
            return
        }
        $SourceId = @($list.SelectedItems | ForEach-Object { [string]$_ })
    } finally { $form.Dispose() }
}
$runName = (Get-Date -Format 'yyyyMMdd_HHmmss') + '_' + ([guid]::NewGuid().ToString('N').Substring(0,8))
$outputPath = Join-Path ([System.IO.Path]::GetFullPath($OutputRoot)) $runName
$arguments = @($scriptPath,'--roster',$RosterPath,'--state',$StatePath,'--output',$outputPath)
foreach ($id in $SourceId) { $arguments += @('--source-id',$id) }
if ($Seed) { $arguments += @('--seed',$Seed) }
Write-Host 'V23 reviewed prototype. Uncertain/not-observed regions remain original. General protection is unverified.'
$response = & $PythonPath @arguments
$code = $LASTEXITCODE
try { $result = ($response -join "`n") | ConvertFrom-Json }
catch { throw "Invalid demo response. Incomplete output (if any): $outputPath" }
if ($code -ne 0 -or $result.status -ne 'completed_reviewed_V23_demo') {
    throw ("V23 demo failed: " + $result.reason + ". Incomplete output (if any): " + $outputPath)
}
Write-Host ('Saved result folder: ' + $result.output)
Write-Host ('Comparison report: ' + $result.report)
if (-not $NoOpen) { Start-Process -FilePath $result.report }
Write-Output $result
