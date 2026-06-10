$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python)) { python -m venv (Join-Path $root ".venv") }

& $python -m pip install -r (Join-Path $root "requirements.txt")
& $python -m compileall main.py core database models repositories services scripts ui workers
$env:QT_QPA_PLATFORM = "offscreen"
& $python (Join-Path $root "scripts\check_responsive.py")
& $python (Join-Path $root "scripts\generate_changelog.py")
& (Join-Path $root "scripts\download_cores.ps1")
& (Join-Path $root "scripts\package_release.ps1")

if (-not (Test-Path -LiteralPath (Join-Path $root ".git"))) {
    git init $root
}
git -C $root config user.name "LuckasApp Deployment"
git -C $root config user.email "actions@luckasapp.local"
git -C $root branch -M main

$remoteUrl = "https://github.com/luckasgh9170/luckasapp.git"
git -C $root remote get-url origin 2>$null
if ($LASTEXITCODE -ne 0) {
    git -C $root remote add origin $remoteUrl
} else {
    git -C $root remote set-url origin $remoteUrl
}
git -C $root add .
git -C $root diff --cached --quiet
if ($LASTEXITCODE -ne 0) {
    git -C $root commit -m "Automated deployment update"
} else {
    Write-Host "No changes to commit."
}
git -C $root push -u origin main
