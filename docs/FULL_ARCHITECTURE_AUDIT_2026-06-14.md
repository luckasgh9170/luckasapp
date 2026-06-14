# LuckasApp Full Architecture Audit

Date: 2026-06-14

## Scope

This audit reviewed the desktop client, Windows background service, GitHub synchronization path, backend processing path, local cache and SQLite usage, Xray core launch path, update flow, and QML UI event flow in `D:\luckasapp`.

The audit was based on direct inspection of the current code, current runtime state, current service logs, current network logs, and current distribution metadata.

## Executive Summary

The project has already completed an important architecture transition: bulk server discovery, benchmarking, and validation are no longer performed by the desktop client during normal runtime. The client now consumes processed server metadata from GitHub and keeps a small local ready list.

The current architecture is directionally correct, but several runtime weaknesses remain:

1. `AppBridge` is still a large orchestration object and remains the main architectural bottleneck.
2. Core process lifecycle management is fragile and can leak handles or collide on fixed ports.
3. One-shot sync and always-on service share the same state file and can temporarily overwrite each other.
4. Traffic statistics are session-scoped in the UI but sourced from system-wide network counters.
5. Several JSON state files are still written non-atomically.
6. Legacy validation code remains in the tree and in some models/settings even though runtime no longer depends on it.

## Current Startup Flow

1. `main.py` configures logging and creates `QGuiApplication`.
2. `AppBridge` is created and injected into QML.
3. `AppBridge` creates:
   - `Database`
   - `SourceRepository`
   - `AsyncRunner`
   - `CoreManager`
   - `ProxyController`
   - `SettingsStore`
   - `HistoryStore`
   - `TrafficMonitor`
   - `ServiceStateStore`
4. QML loads `ui/Main.qml`.
5. Timers start:
   - 1 second UI refresh timer
   - GitHub auto-sync timer
   - failed-config cleanup timer
6. If enabled, `autoSyncFromGitHub()` is scheduled after 900ms.
7. If enabled, update check is scheduled after 1600ms.

## Current Service Flow

1. Windows SCM hosts `scripts/windows_service.py`.
2. `windows_service.py` dispatches to `services/windows_service_entry.py`.
3. `LuckasAppWindowsService.SvcDoRun()` calls `asyncio.run(BackgroundServiceRuntime.run_forever())`.
4. Every sync cycle:
   - read processed server metadata from GitHub
   - merge into SQLite
   - prune removed servers from local cache
   - write `cache/service_status.json`
   - append to `logs/service.log`

## Connection Flow

User Click Connect
-> `AppBridge.connectConfig()`
-> `_connect_config()`
-> export runtime config through `services/xray_exporter.py`
-> `CoreManager.start()`
-> local Xray HTTP inbound starts
-> `verify_proxy_connection()` tests DNS and outbound reachability through the proxy
-> on success: update connection state, traffic session, history, optional system proxy
-> on failure: mark failure and optionally fail over to next ready node

## GitHub Synchronization Flow

Client / Service
-> `GitHubDatasetClient.sync()`
-> `version.json`
-> `data/server_metadata.json`
-> `data/servers.json` or `data/healthy.json`
-> `dataset_record_to_config()`
-> `Database.upsert_configs()`
-> `Database.prune_to_processed()`
-> local SQLite becomes the ready cache

## Backend Processing Flow

Raw dataset
-> `DatasetStore.records()`
-> `ServerProcessingPipeline.validate_distribution()`
-> `HealthChecker.check_many()`
-> `write_processed_servers()`
-> publish `distribution/data/servers.json`
-> scheduled GitHub workflow commits processed outputs

## Measured Runtime State

- Current service state:
  - `Running`
  - sync interval: `300s`
  - local ready records: `12`
- Current local config stats:
  - `total=12`
  - `ready=12`
  - `bestPing=147`
  - `averagePing=570`
- Current offscreen responsive smoke runtime:
  - about `3633 ms`
- Current service log confirms regular 5-minute syncs.
- Current core log contains repeated port bind failures on `127.0.0.1:10808`.

## Architecture Findings

### High Severity

1. Fixed local inbound ports can break connection establishment.
   - Evidence:
     - `logs/core.log` shows repeated `failed to listen TCP on 127.0.0.1:10808`.
     - `ui/bridge.py` always uses configured `socks_port` and `http_port`.
     - `services/xray_exporter.py` emits those ports directly.
   - Impact:
     - connection attempts fail even when the remote node is valid
     - failover can retry multiple good nodes and still fail locally
   - Root cause:
     - fixed local ports assume exclusive ownership
   - Risk:
     - high user-facing reliability issue

2. `CoreManager` process lifecycle is fragile and leaks the log file handle.
   - Evidence:
     - `core/core_manager.py:50-56` opens `log_handle` and never stores or closes it
     - `start()` calls `await stop()` but does not serialize concurrent starts/stops
   - Impact:
     - handle leaks
     - unreliable restart behavior
     - port release timing can be inconsistent

3. `TrafficMonitor` reports system-wide traffic as per-session VPN traffic.
   - Evidence:
     - `services/traffic.py:65` uses `psutil.net_io_counters()`
     - session starts only reset deltas, not network scope
   - Impact:
     - dashboard statistics are misleading
     - bandwidth numbers do not represent the active tunnel

### Medium Severity

4. One-shot sync overwrites shared service state.
   - Evidence:
     - `services/background_sync.py:37-41` writes `Running` then `Stopped` in `run_once()`
     - service and one-shot daemon both use `cache/service_status.json`
   - Impact:
     - transient incorrect service state in UI and diagnostics
     - confusing operator experience

5. `AsyncRunner` has no shutdown path.
   - Evidence:
     - `workers/async_runner.py` starts a daemon loop thread but exposes no close method
   - Impact:
     - thread survives until process exit
     - difficult to test and reason about cleanup

6. State/config JSON writes are not atomic in several stores.
   - Evidence:
     - `services/settings.py:67,87`
     - `services/service_state.py:43`
     - `services/updater.py:73,77`
   - Impact:
     - risk of partial/corrupt files during interruption or concurrent writes

7. `AppBridge` remains a god object.
   - Evidence:
     - `ui/bridge.py` contains sync orchestration, connect orchestration, update orchestration, service control, history, traffic, settings, diagnostics
   - Impact:
     - low testability
     - higher regression risk
     - harder future maintenance

### Low Severity

8. Legacy validation architecture remains in tree after processed-server redesign.
   - Evidence:
     - `services/health.py`
     - `services/server_processing.py` still depends on it for backend validation
     - UI methods now no-op but validation signals/properties remain
   - Impact:
     - conceptual overhead
     - larger maintenance surface

9. Local distribution artifacts can diverge from what the service has synced from GitHub.
   - Evidence:
     - local `distribution/data/server_metadata.json` showed `processed_servers=2`
     - runtime service state showed `records=12`
   - Impact:
     - repo-local artifacts are not a trustworthy runtime source by themselves

## Security Findings

1. TLS certificate verification is enabled in runtime verification and health checks.
   - Status: good
2. Update ZIP extraction guards against path traversal.
   - Status: good
3. Sensitive configuration storage is not encrypted.
   - Evidence:
     - raw configs remain in SQLite and exported files
   - Risk:
     - local-machine compromise exposes secrets
4. System proxy changes do not preserve and restore the prior proxy configuration.
   - Risk:
     - user environment may be left altered after abnormal exit

## Windows Service Health Report

Observed status:
- service installed
- service set to automatic
- service running successfully
- regular sync cadence visible in log

Residual risks:
- shared state file with one-shot daemon
- no explicit service recovery policy setup in the installer
- no structured IPC beyond shared JSON status/log files

## Performance Report

Current improvements already in place:
- client no longer bulk-validates nodes on startup
- GitHub sync is asynchronous
- service sync is decoupled from UI

Remaining bottlenecks:
- `AppBridge` refresh model still re-queries whole lists often
- `TrafficMonitor` samples every second regardless of actual tunnel state
- some file writes are synchronous on the UI side

## Dead / Legacy / Duplicate Code

- `validationRunning` remains exposed in `AppBridge` and QML but runtime validation is disabled
- source repository management remains in desktop runtime although normal processed-server flow no longer depends on it
- local distribution build scripts remain useful for backend/publishing, but not for normal client runtime

## Recommended Refactor Order

1. Stabilize runtime process lifecycle and local inbound port allocation.
2. Fix state-file ownership between service and one-shot sync.
3. Add `AsyncRunner` shutdown and deterministic app cleanup.
4. Make JSON state/config writes atomic.
5. Separate `AppBridge` into:
   - sync controller
   - connection controller
   - update controller
   - diagnostics facade
6. Redesign tunnel traffic measurement so it reflects tunnel/proxy traffic rather than total system I/O.

## Implemented Fixes In This Audit Pass

The code changes in this pass should be limited to findings confirmed by inspection:

1. fix `AsyncRunner` lifecycle
2. fix `CoreManager` log handle and restart serialization
3. fix one-shot service state overwrite behavior
4. fix local inbound port collision during connect by selecting free local ports when configured ones are unavailable

## Future Maintenance Recommendations

- Introduce a small `atomic_json.py` helper and use it everywhere state is written.
- Move service and one-shot status into separate channels or add ownership markers.
- Split `AppBridge` before adding more UI features.
- Add an integration smoke test for:
  - sync
  - connect
  - failover
  - service run-once
  - service restart
