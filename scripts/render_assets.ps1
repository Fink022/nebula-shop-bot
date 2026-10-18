$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$edge = "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
if (-not (Test-Path $edge)) { $edge = "C:\Program Files\Microsoft\Edge\Application\msedge.exe" }
if (-not (Test-Path $edge)) { throw "Microsoft Edge not found" }

New-Item -ItemType Directory -Force -Path "$root\assets\products" | Out-Null

function Render-Png {
    param($Url, $OutPath, $Width, $Height, $Tag)
    $profile = Join-Path $env:TEMP "nebula-render-$Tag"
    $process = Start-Process -FilePath $edge -PassThru -WindowStyle Hidden -ArgumentList @(
        "--headless=new", "--disable-gpu", "--hide-scrollbars",
        "--force-device-scale-factor=1", "--window-size=$Width,$Height",
        "--virtual-time-budget=3000", "--no-first-run",
        "--user-data-dir=$profile", "--screenshot=$OutPath", $Url
    )
    $process.WaitForExit(30000) | Out-Null
    Start-Sleep -Milliseconds 800
}

$bannerUrl = ([System.Uri]::new("$root\scripts\banner.html")).AbsoluteUri
Render-Png -Url $bannerUrl -OutPath "$root\assets\banner.png" -Width 1280 -Height 640 -Tag "banner"

$productUrl = ([System.Uri]::new("$root\scripts\product.html")).AbsoluteUri
foreach ($i in 0..5) {
    Render-Png -Url "$($productUrl)?p=$i" -OutPath "$root\assets\products\p$i.png" -Width 800 -Height 800 -Tag "p$i"
}

Write-Host "Done: assets\banner.png + assets\products\p0..p5.png"
