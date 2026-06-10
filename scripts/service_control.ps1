param(
    [ValidateSet("install", "update", "start", "stop", "restart", "status", "remove", "run-once")]
    [string]$Action = "status"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root ".venv\Scripts\python.exe"
$serviceScript = Join-Path $root "scripts\windows_service.py"
$daemonScript = Join-Path $root "scripts\background_daemon.py"
$serviceName = "LuckasAppBackgroundService"

if (-not (Test-Path -LiteralPath $python)) {
    throw "Python venv not found: $python"
}

function Register-ProjectPath {
    $site = & $python -c "import sysconfig; print(sysconfig.get_paths()['purelib'])"
    $pth = Join-Path $site "luckasapp.pth"
    Set-Content -LiteralPath $pth -Value $root -Encoding ASCII
    $basePrefix = & $python -c "import sys; print(sys.base_prefix)"
    $venvRoot = Split-Path -Parent (Split-Path -Parent $python)
    foreach ($dll in @("python3.dll", "python314.dll", "python313.dll", "python312.dll", "python311.dll")) {
        $source = Join-Path $basePrefix $dll
        if (Test-Path -LiteralPath $source) {
            Copy-Item -LiteralPath $source -Destination $venvRoot -Force
        }
    }
    $pywin32DllDir = Join-Path $site "pywin32_system32"
    if (Test-Path -LiteralPath $pywin32DllDir) {
        Get-ChildItem -LiteralPath $pywin32DllDir -Filter "*.dll" | Copy-Item -Destination $venvRoot -Force
    }
}

switch ($Action) {
    "install" {
        & $python -m pip install pywin32
        Register-ProjectPath
        & $python $serviceScript --startup auto install
        & $python $serviceScript start
    }
    "update" {
        & $python -m pip install pywin32
        Register-ProjectPath
        & $python $serviceScript --startup auto update
    }
    "start" {
        & $python $serviceScript start
    }
    "stop" {
        & $python $serviceScript stop
    }
    "restart" {
        & $python $serviceScript restart
    }
    "remove" {
        & $python $serviceScript stop 2>$null
        & $python $serviceScript remove
    }
    "run-once" {
        & $python $daemonScript --once
    }
    "status" {
        $svc = Get-Service -Name $serviceName -ErrorAction SilentlyContinue
        if ($svc) {
            $svc | Select-Object Name,DisplayName,Status,StartType
        } else {
            Write-Host "Service is not installed."
        }
        $statusPath = Join-Path $root "cache\service_status.json"
        if (Test-Path -LiteralPath $statusPath) {
            Get-Content -LiteralPath $statusPath -Raw
        }
    }
}
