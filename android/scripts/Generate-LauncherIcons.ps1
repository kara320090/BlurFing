param([string]$StoreIconPath)

$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing
$androidDirectory = Split-Path $PSScriptRoot -Parent
$resourceDirectory = Join-Path $androidDirectory 'app\src\main\res'
$master = New-Object System.Drawing.Bitmap 1024, 1024
$graphics = [System.Drawing.Graphics]::FromImage($master)
$shield = New-Object System.Drawing.Drawing2D.GraphicsPath
$ridges = New-Object System.Drawing.Drawing2D.GraphicsPath
$shieldFill = New-Object System.Drawing.SolidBrush ([System.Drawing.ColorTranslator]::FromHtml('#17344D'))
$shieldPen = New-Object System.Drawing.Pen ([System.Drawing.ColorTranslator]::FromHtml('#E2F5F3')), 2.5
$ridgePen = New-Object System.Drawing.Pen ([System.Drawing.ColorTranslator]::FromHtml('#73E5C9')), 2.7
try {
    $graphics.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
    $graphics.Clear([System.Drawing.ColorTranslator]::FromHtml('#0B1424'))
    $graphics.ScaleTransform((1024.0 / 108), (1024.0 / 108))
    $shieldPen.LineJoin = [System.Drawing.Drawing2D.LineJoin]::Round
    $ridgePen.StartCap = [System.Drawing.Drawing2D.LineCap]::Round
    $ridgePen.EndCap = [System.Drawing.Drawing2D.LineCap]::Round
    $shield.AddLine(54, 25, 77, 34)
    $shield.AddLine(77, 34, 77, 53)
    $shield.AddBezier(77, 53, 77, 67, 66, 77, 54, 83)
    $shield.AddBezier(54, 83, 42, 77, 31, 67, 31, 53)
    $shield.AddLine(31, 53, 31, 34)
    $shield.CloseFigure()
    $graphics.FillPath($shieldFill, $shield)
    $graphics.DrawPath($shieldPen, $shield)
    $ridges.AddBezier(39, 54, 39, 34, 69, 34, 69, 54)
    $ridges.StartFigure()
    $ridges.AddLine(44, 59, 44, 53)
    $ridges.AddBezier(44, 53, 44, 40, 64, 40, 64, 53)
    $ridges.AddLine(64, 53, 64, 60)
    $ridges.StartFigure()
    $ridges.AddLine(49, 65, 49, 53)
    $ridges.AddBezier(49, 53, 49, 47, 59, 47, 59, 53)
    $ridges.AddLine(59, 53, 59, 64)
    $ridges.StartFigure()
    $ridges.AddLine(54, 55, 54, 72)
    $ridges.StartFigure()
    $ridges.AddBezier(38, 60, 39, 65, 41, 69, 45, 72)
    $ridges.StartFigure()
    $ridges.AddLine(68, 66, 65, 71)
    $graphics.DrawPath($ridgePen, $ridges)

    $sizes = [ordered]@{ mdpi = 48; hdpi = 72; xhdpi = 96; xxhdpi = 144; xxxhdpi = 192 }
    foreach ($density in $sizes.Keys) {
        $directory = Join-Path $resourceDirectory "mipmap-$density"
        New-Item -ItemType Directory -Path $directory -Force | Out-Null
        $size = $sizes[$density]
        $bitmap = New-Object System.Drawing.Bitmap $size, $size
        $scaled = [System.Drawing.Graphics]::FromImage($bitmap)
        try {
            $scaled.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
            $scaled.DrawImage($master, 0, 0, $size, $size)
            $bitmap.Save((Join-Path $directory 'ic_launcher.png'), [System.Drawing.Imaging.ImageFormat]::Png)
            $bitmap.Save((Join-Path $directory 'ic_launcher_round.png'), [System.Drawing.Imaging.ImageFormat]::Png)
        } finally { $scaled.Dispose(); $bitmap.Dispose() }
    }
    if ($StoreIconPath) {
        $store = New-Object System.Drawing.Bitmap 512, 512
        $storeGraphics = [System.Drawing.Graphics]::FromImage($store)
        try {
            $storeGraphics.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
            $storeGraphics.DrawImage($master, 0, 0, 512, 512)
            $store.Save([System.IO.Path]::GetFullPath($StoreIconPath), [System.Drawing.Imaging.ImageFormat]::Png)
        } finally { $storeGraphics.Dispose(); $store.Dispose() }
    }
    Write-Output 'BlurFing launcher icons generated for five densities.'
} finally {
    $ridgePen.Dispose(); $shieldPen.Dispose(); $shieldFill.Dispose()
    $ridges.Dispose(); $shield.Dispose(); $graphics.Dispose(); $master.Dispose()
}
