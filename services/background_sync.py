from __future__ import annotations

import asyncio
import time
from pathlib import Path
from threading import Event

from database.db import Database
from services.github_sync import GitHubDatasetClient
from services.service_state import ServiceStateStore, utc_now
from services.settings import SettingsStore


class BackgroundServiceRuntime:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.settings = SettingsStore(root)
        self.db = Database(root)
        self.state = ServiceStateStore(root)
        self._last_sync = 0.0

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
        self._cleanup_cache()
        self.state.write(status="Stopped")

    async def run_cycle(self) -> None:
        now = time.monotonic()
        sync_interval = max(1, int(self.settings.get("sync_interval", 5) or 5)) * 60
        if now - self._last_sync >= sync_interval:
            await self._sync_backend(force=False)
            self._last_sync = now
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
            purged = self.db.purge_remote_removed()
            if purged > 0:
                self.state.log("cleanup", f"Purged {purged} configs removed from processed GitHub list")
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
                modified_records=result.get("modified_records", 0),
                removed_records=result.get("removed_records", 0),
                purged_records=result.get("purged_records", 0),
                last_processed_update=result.get("processed_at", ""),
            )
            self.state.log(
                "sync",
                (
                    "GitHub sync complete: "
                    f"{result.get('new_records', 0)} new, "
                    f"{result.get('modified_records', 0)} modified, "
                    f"{result.get('removed_records', 0)} removed, "
                    f"{result.get('purged_records', 0)} purged"
                ),
                remote_version=result.get("remote_version", ""),
            )
        except Exception as exc:
            self.state.write(status="Error", last_error=f"Sync failed: {exc}")
            self.state.log("sync_error", str(exc))

    def _cleanup_cache(self) -> None:
        max_mb = int(self.settings.get("cache_size_mb", 512) or 512)
        max_bytes = max_mb * 1024 * 1024
        cache = self.root / "cache"
        if not cache.exists():
            return
        files: list[tuple[Path, int, float]] = []
        total = 0
        for path in cache.rglob("*"):
            if not path.is_file():
                continue
            try:
                stat = path.stat()
            except FileNotFoundError:
                continue
            files.append((path, stat.st_size, stat.st_mtime))
            total += stat.st_size
        if total <= max_bytes:
            return
        removable = sorted(
            [item for item in files if "health-tests" in item[0].parts or "updates" in item[0].parts],
            key=lambda item: item[2],
        )
        for path, size, _mtime in removable:
            try:
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
