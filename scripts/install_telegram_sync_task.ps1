$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root ".venv\Scripts\pythonw.exe"
$script = Join-Path $root "scripts\telegram_daemon.py"

if (-not (Test-Path -LiteralPath $python)) {
    throw "Python venv not found: $python"
}

if (-not $env:TELEGRAM_API_ID -or -not $env:TELEGRAM_API_HASH) {
    throw "Set TELEGRAM_API_ID and TELEGRAM_API_HASH before installing the sync task."
}

$taskName = "LuckasApp Telegram GitHub Sync"
$arguments = "`"$script`" --channel ConfigsHUB2 --interval 300 --limit 300 --publish"
$action = New-ScheduledTaskAction -Execute $python -Argument $arguments -WorkingDirectory $root
$trigger = New-ScheduledTaskTrigger -AtLogOn
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -Force | Out-Null
Write-Host "Installed scheduled task: $taskName"
