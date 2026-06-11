# LuckasApp Technical Audit

Date: 2026-06-11

## Scope

Reviewed and hardened the VPN/proxy client architecture around connectivity, GitHub synchronization, background service behavior, async execution, backend communication, UI state, and security.

## Findings And Fixes

### Network Connectivity

- Runtime Xray config generation now includes DNS and routing sections with explicit DNS strategy.
- Connection export was moved off the UI thread to avoid blocking the desktop during CA/DNS/config work.
- Post-connect verification now checks DNS, TLS, route and outbound HTTP reachability through the local Xray HTTP inbound.
- Smart Connect now performs failover across ranked healthy nodes when verification fails.
- System proxy automation was implemented for Windows registry proxy settings, gated by `set_system_proxy_on_connect`.

### Synchronization

- GitHub sync now uses a shared `ApiClient` with timeouts, retries, request logging and a circuit breaker.
- Version cache writes are atomic.
- Remote dataset sync now keeps a local index and detects added, modified and removed records.
- Records removed from the GitHub distribution are marked offline with score `0` so they are excluded from recommendations and auto-connect.
- Desktop sync now consumes only `distribution/data/servers.json` or `healthy.json`, which are preprocessed backend outputs.
- Subscription collection uses the same API client and no longer creates one HTTP client per source.
- Background service no longer runs server health checks locally; it synchronizes processed server metadata every configured interval and maintains cache consistency.

### Server Processing

- Added backend-only server processing pipeline in `services/server_processing.py`.
- Added `scripts/process_server_health.py` for scheduled validation, ranking and processed server publication.
- Added GitHub Actions workflow `Process Healthy Servers` to run backend validation and commit `servers.json`, `healthy.json`, `server_metadata.json`, and distribution version metadata.
- Processed server records include `ping`, `health`, `stability`, `score`, `status`, and `last_check`.

### Performance

- Heavy connection config export no longer blocks QML/main thread.
- GitHub distribution publishing from the desktop bridge now runs in a background worker.
- Client startup no longer triggers bulk ping, benchmarking, discovery, ranking or validation.
- Desktop UI loads cached SQLite servers immediately and only performs lightweight connect-time verification for the selected node.
- GitHub sync and backend calls remain on background asyncio workers.
- HTTP connection pooling is centralized in `ApiClient`.

### Backend Reliability

- Added retry policy, timeout handling, request diagnostics and circuit breaker behavior.
- Network diagnostics are written to `logs/network.jsonl`.
- Application logs are written to `logs/app.log`.

### Security

- Removed insecure TLS verification bypass from connection verification.
- Removed `CERT_NONE` TLS probe behavior; TLS probes now use default certificate validation.
- Update zip extraction is protected against path traversal.
- Xray TLS outbound keeps `allowInsecure` false.
- Malformed dataset entries are validated through Pydantic models before insertion.
- GitHub dataset downloads reject non-list JSON payloads before writing local storage.

## Remaining Operational Constraints

- Full TUN mode still requires administrator privileges and a supported Windows TUN driver. Current UI exposes warnings and guarded controls; route/firewall kill-switch implementation remains OS-level work.
- DNS leak prevention is reliable for proxied traffic through Xray. OS-wide DNS leak prevention requires TUN/firewall integration.
- A mathematical 99% connection success rate cannot be guaranteed for public free nodes because upstream nodes are unstable. The implemented behavior improves success by excluding unhealthy nodes and failing over automatically.
