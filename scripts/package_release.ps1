$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$dist = Join-Path $root "release"
$packageRoot = Join-Path $dist "LuckasApp"
$zip = Join-Path $dist "LuckasApp-windows.zip"

if (Test-Path -LiteralPath $packageRoot) { Remove-Item -LiteralPath $packageRoot -Recurse -Force }
New-Item -ItemType Directory -Force -Path $packageRoot | Out-Null

$include = @(
    "main.py", "requirements.txt", "pyproject.toml", "README.md", "CHANGELOG.md", "version.json",
    "core", "database", "models", "repositories", "services", "workers", "ui",
    "scripts", "distribution"
)

foreach ($item in $include) {
    $source = Join-Path $root $item
    if (Test-Path -LiteralPath $source) {
        Copy-Item -LiteralPath $source -Destination $packageRoot -Recurse -Force
    }
}

Get-ChildItem -Path $packageRoot -Recurse -Directory -Filter "__pycache__" | Remove-Item -Recurse -Force
if (Test-Path -LiteralPath $zip) { Remove-Item -LiteralPath $zip -Force }
Compress-Archive -Path (Join-Path $packageRoot "*") -DestinationPath $zip -Force
Get-Item -LiteralPath $zip | Select-Object FullName,Length
