$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $python)) {
    python -m venv (Join-Path $root ".venv")
}

& $python -m pip install -r (Join-Path $root "requirements.txt")
& (Join-Path $PSScriptRoot "download_cores.ps1")
$env:PYTHONIOENCODING = "utf-8"
& $python (Join-Path $PSScriptRoot "discover_repositories.py") --limit 25 --max-repos 40 --save-sources
& $python (Join-Path $PSScriptRoot "refresh_configs.py")
