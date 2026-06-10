# LuckasApp

Modern Python desktop client manager scaffold for V2Ray/Xray.

## Run

```powershell
cd D:\luckasapp
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python main.py
```

## Features in this build

- Simplified premium VPN UI with working sidebar pages: Home, Scan, Servers, Favorites, Statistics, History and Settings
- Large Quick Connect control, central SCAN action, modern cards, responsive layouts and live progress bar
- GitHub-backed dataset metadata, 5-minute auto sync, auto-update check on startup, Update Now, Later and Skip Version actions
- GitHub Actions workflows for CI, release packaging, changelog generation and version management
- Async subscription collector and parser for `vmess`, `vless`, `trojan`, `ss`, `hysteria` and `tuic`
- SQLite persistence via SQLAlchemy and local cache storage
- YouTube reachability validation for `youtube.com` and `www.youtube.com`
- Real-time validation queue with DNS, TCP, TLS/Reality hints, Xray runtime tests and immediate Ready-node connection
- Server cards with country, protocol, ping, score, status, Connect, Copy, Favorite and Details actions
- Real Proxy Mode through Xray local SOCKS/HTTP inbounds
- Smart Connect selects the highest-ranked Ready node
- Real-time traffic monitor with upload/download speed, peaks, session usage and daily/monthly/lifetime counters

VPN/TUN controls are present and guarded. Full OS-wide VPN routing requires administrator privileges, TUN/Wintun driver setup, route management, DNS routing and kill-switch firewall rules on the target machine.

Place `xray.exe` or `v2ray.exe` inside `core/bin` or configure its path later.

## GitHub deployment and updates

Default GitHub profile:

```text
luckasgh9170/luckasapp
```

Main update metadata file:

```text
https://raw.githubusercontent.com/luckasgh9170/luckasapp/main/version.json
```

Release asset URL used by the client updater:

```text
https://github.com/luckasgh9170/luckasapp/releases/latest/download/LuckasApp-windows.zip
```

Run local validation, packaging and GitHub push:

```powershell
cd D:\luckasapp
.\scripts\deploy_to_github.ps1
```

Bump version metadata locally:

```powershell
.\.venv\Scripts\python.exe .\scripts\bump_version.py --version 1.0.1 --notes "Release notes"
```

Generate changelog:

```powershell
.\.venv\Scripts\python.exe .\scripts\generate_changelog.py
```

Package release zip:

```powershell
.\scripts\package_release.ps1
```

## Telegram to GitHub auto sync

The automated chain is:

```text
Telegram Channel -> Telegram daemon -> distribution JSON -> GitHub commit/push -> Desktop SCAN/auto-sync -> SQLite/UI
```

The daemon polls every 5 minutes by default:

```powershell
cd D:\luckasapp
$env:TELEGRAM_API_ID="your_api_id"
$env:TELEGRAM_API_HASH="your_api_hash"
.\.venv\Scripts\python.exe .\scripts\telegram_daemon.py --channel ConfigsHUB2 --interval 300 --limit 300 --publish
```

Install the Windows scheduled task after setting Telegram credentials:

```powershell
.\scripts\install_telegram_sync_task.ps1
```

GitHub dataset files are generated in `distribution/`:

```text
data/latest.json
data/archive.json
data/metadata.json
data/stats.json
version.json
```

Every publish commit uses an automatic message like:

```text
Auto Sync Update 2026-06-10T00:00:00Z Record Count 1200
```

## Download official cores from GitHub

```powershell
cd D:\luckasapp
.\scripts\download_cores.ps1
```

## Discover public repositories from GitHub

```powershell
cd D:\luckasapp
python .\scripts\discover_repositories.py --limit 25 --max-repos 40 --save-sources
```

Discovery output is saved to `cache/discovered_repositories.json`, repository metadata is stored in SQLite, and raw URLs are added to `cache/sources.json`.

## Collect configs from saved sources

```powershell
cd D:\luckasapp
python .\scripts\refresh_configs.py
```

## One-command update

```powershell
cd D:\luckasapp
.\scripts\update_all.ps1
```

## Telegram to GitHub distribution

Authorized channel collector for `ConfigsHUB2`:

```powershell
cd D:\luckasapp
$env:TELEGRAM_API_ID="your_api_id"
$env:TELEGRAM_API_HASH="your_api_hash"
.\.venv\Scripts\python.exe .\scripts\telegram_sync_publish.py --channel ConfigsHUB2 --limit 300
```

Continuous collector:

```powershell
.\.venv\Scripts\python.exe .\scripts\telegram_daemon.py --channel ConfigsHUB2 --interval 300 --publish
```

Build GitHub distribution files from the local database:

```powershell
.\.venv\Scripts\python.exe .\scripts\build_distribution.py
```

The generated GitHub-ready backend is in `distribution/`:

- `version.json`
- `index.json`
- `data/latest.json`
- `data/archive.json`
- `data/metadata.json`
- `data/stats.json`
- `data/latest/latest.json` legacy compatibility copy
- `data/archive/*.json`
- `stats/stats.json`

To publish, make `distribution/` a git repository or clone your GitHub repo there, then:

```powershell
.\.venv\Scripts\python.exe .\scripts\publish_distribution.py --message "Update ConfigsHUB2 dataset"
```

Client SCAN uses a raw GitHub base URL such as:

```text
https://raw.githubusercontent.com/<owner>/<repo>/<branch>
```

Set it in `Settings -> Updates` or the Scan page, then press `SCAN`.

## Desktop launcher

The installer step creates `LuckasApp.bat` and `LuckasApp.lnk` on the Windows desktop.

## Responsive smoke test

```powershell
cd D:\luckasapp
$env:QT_QPA_PLATFORM='offscreen'
.\.venv\Scripts\python.exe .\scripts\check_responsive.py
```
