from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Event

from database.db import Database
from services.github_sync import GitHubDatasetClient
from services.health import HealthChecker, is_ready_status
from services.service_state import ServiceStateStore, utc_now
from services.settings import SettingsStore


class BackgroundServiceRuntime:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.settings = SettingsStore(root)
        self.db = Database(root)
        self.state = ServiceStateStore(root)
        self.health = HealthChecker(root=root, timeout=float(self.settings.get("validation_timeout", 8)))
        self._last_sync = 0.0
        self._last_health = 0.0

    async def run_forever(self, stop_event: Event | None = None) -> None:
        self.state.write(status="Running", last_error="")
        self.state.log("service", "Background service started")
        try:
            while not _should_stop(stop_event):
                await self.run_cycle()
                await self._sleep(stop_event, 5)
        except Exception as exc:
            self.state.write(status="Error", last_error=str(exc))
            self.state.log("error", str(exc))
            raise
        finally:
            self.state.write(status="Stopped")
            self.state.log("service", "Background service stopped")

    async def run_once(self) -> None:
        self.state.write(status="Running", last_error="")
        await self._sync_backend(force=True)
        await self._health_check()
        self._cleanup_cache()
        self.state.write(status="Stopped")

    async def run_cycle(self) -> None:
        now = time.monotonic()
        sync_interval = max(1, int(self.settings.get("sync_interval", 5) or 5)) * 60
        health_interval = max(1, int(self.settings.get("service_health_interval", 5) or 5)) * 60
        if now - self._last_sync >= sync_interval:
            await self._sync_backend(force=False)
            self._last_sync = now
        if now - self._last_health >= health_interval:
            await self._health_check()
            self._last_health = now
        self._cleanup_cache()
        self._cleanup_failed_configs()
        stats = self.db.config_stats()
        self.state.write(
            status="Running",
            records=stats.get("total", 0),
            healthy=stats.get("ready", 0),
            service_interval_seconds=sync_interval,
        )

    def _cleanup_failed_configs(self) -> None:
        min_failures = max(1, int(self.settings.get("cleanup_min_failures", 5) or 5))
        max_age_hours = max(1, int(self.settings.get("cleanup_max_age_hours", 48) or 48))
        try:
            removed = self.db.delete_failed_configs(min_failures=min_failures, max_age_hours=max_age_hours)
            if removed > 0:
                self.state.log("cleanup", f"Removed {removed} failed configs from database")
        except Exception as exc:
            self.state.log("cleanup_error", f"Failed to remove dead configs: {exc}")

    async def _sync_backend(self, force: bool) -> None:
        base_url = str(self.settings.get("github_distribution_base_url", "")).strip()
        if not base_url:
            self.state.write(status="Error", last_error="GitHub distribution URL is not configured.")
            return
        self.state.write(status="Updating", last_error="")
        try:
            result = await GitHubDatasetClient(self.root, base_url).sync(force=force)
            self.state.write(
                status="Running",
                last_sync=utc_now(),
                remote_version=result.get("remote_version", ""),
                records=result.get("records", 0),
                new_records=result.get("new_records", 0),
            )
            self.state.log(
                "sync",
                f"GitHub sync complete: {result.get('new_records', 0)} new records",
                remote_version=result.get("remote_version", ""),
            )
        except Exception as exc:
            self.state.write(status="Error", last_error=f"Sync failed: {exc}")
            self.state.log("sync_error", str(exc))

    async def _health_check(self) -> None:
        candidates = self._health_candidates()
        if not candidates:
            self.state.write(status="Running", last_health_check=utc_now())
            return
        self.state.write(status="Updating", last_error="")
        limit = max(1, int(self.settings.get("service_validation_workers", self.settings.get("validation_workers", 4)) or 4))

        def stage(config) -> None:
            self.db.upsert_configs([config])

        try:
            checked = await self.health.check_many(candidates, limit=limit, stage_callback=stage)
            self.db.upsert_configs(checked)
            ready = sum(1 for item in checked if is_ready_status(item.status.value))
            self.state.write(status="Running", last_health_check=utc_now(), last_health_ready=ready)
            self.state.log("health", f"Checked {len(checked)} nodes, {ready} healthy")
        except Exception as exc:
            self.state.write(status="Error", last_error=f"Health check failed: {exc}")
            self.state.log("health_error", str(exc))

    def _health_candidates(self):
        batch = max(1, int(self.settings.get("service_health_batch", 24) or 24))
        max_age = int(self.settings.get("service_health_max_age_minutes", 60) or 60)
        cutoff = datetime.now(UTC) - timedelta(minutes=max_age)
        configs = self.db.list_configs(limit=1000)

        def stale(item) -> bool:
            if not item.last_check_at:
                return True
            try:
                value = datetime.fromisoformat(item.last_check_at.replace("Z", "+00:00"))
                return value < cutoff
            except Exception:
                return True

        configs.sort(
            key=lambda item: (
                is_ready_status(item.status.value),
                not stale(item),
                item.ping_ms if item.ping_ms is not None else 999999,
                -item.score,
            )
        )
        return configs[:batch]

    def _cleanup_cache(self) -> None:
        max_mb = int(self.settings.get("cache_size_mb", 512) or 512)
        max_bytes = max_mb * 1024 * 1024
        cache = self.root / "cache"
        if not cache.exists():
            return
        files = [path for path in cache.rglob("*") if path.is_file()]
        total = sum(path.stat().st_size for path in files)
        if total <= max_bytes:
            return
        removable = sorted(
            [path for path in files if "health-tests" in path.parts or "updates" in path.parts],
            key=lambda item: item.stat().st_mtime,
        )
        for path in removable:
            try:
                size = path.stat().st_size
                path.unlink()
                total -= size
                if total <= max_bytes:
                    break
            except Exception:
                continue

    async def _sleep(self, stop_event: Event | None, seconds: int) -> None:
        for _ in range(seconds * 10):
            if _should_stop(stop_event):
                return
            await asyncio.sleep(0.1)


def _should_stop(stop_event: Event | None) -> bool:
    return bool(stop_event and stop_event.is_set())
