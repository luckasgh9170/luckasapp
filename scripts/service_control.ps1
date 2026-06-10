param(
    [ValidateSet("install", "start", "stop", "restart", "status", "remove", "run-once")]
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

switch ($Action) {
    "install" {
        & $python -m pip install pywin32
        & $python $serviceScript install --startup auto
        & $python $serviceScript start
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
