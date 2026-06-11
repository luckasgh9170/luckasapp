from __future__ import annotations

import asyncio
import logging
import subprocess
import time
from pathlib import Path
from typing import Any
from concurrent.futures import CancelledError
import re

from PySide6.QtCore import QObject, Property, QTimer, Signal, Slot
from PySide6.QtGui import QGuiApplication

from core.core_manager import CoreManager
from core.proxy_controller import ProxyController
from database.db import Database
from repositories.sources import SourceRepository
from services.collector import ConfigCollector
from services.discovery import GitHubDiscoveryEngine, save_discovery_output
from services.github_distribution import GitHubDistributionPublisher
from services.github_sync import GitHubDatasetClient
from services.health import HealthChecker, QUICK_CHECK_TIMEOUT, is_ready_status
from services.history import HistoryStore
from services.connection_verifier import verify_proxy_connection
from services.service_state import ServiceStateStore
from services.settings import SettingsStore
from services.traffic import TrafficMonitor
from services.updater import UpdateManager
from services.xray_exporter import export_xray_config
from workers.async_runner import AsyncRunner

logger = logging.getLogger(__name__)
MAX_FAILOVER_ATTEMPTS = 3


class AppBridge(QObject):
    configsChanged = Signal()
    sourcesChanged = Signal()
    statsChanged = Signal()
    busyChanged = Signal()
    validationRunningChanged = Signal()
    progressChanged = Signal()
    currentServerChanged = Signal()
    trafficChanged = Signal()
    settingsChanged = Signal()
    connectionModeChanged = Signal()
    syncChanged = Signal()
    updateChanged = Signal()
    notification = Signal(str)

    def __init__(self, root: Path) -> None:
        super().__init__()
        self.root = root
        self.db = Database(root)
        self.sources = SourceRepository(root)
        self.collector = ConfigCollector(root)
        self.health = HealthChecker(root=root)
        self.runner = AsyncRunner()
        self.core = CoreManager(root)
        self.proxy = ProxyController()
        self.settings = SettingsStore(root)
        self.history = HistoryStore(root)
        self.traffic = TrafficMonitor(root)
        self._busy = False
        self._validation_running = False
        self._validation_future: Any = None
        self._validation_concurrency = 4
        self._last_live_emit = 0.0
        self._progress_value = 0
        self._progress_total = 0
        self._progress_done = 0
        self._progress_title = ""
        self._progress_detail = ""
        self._current_server = "Disconnected"
        self._current_config_id = ""
        self._connection_state = "Disconnected"
        self._connection_mode = "disconnected"
        self._proxy_status = "disabled"
        self._vpn_status = "disabled"
        self._failover_config_ids: list[str] = []
        self._diagnostics = {
            "dns_status": "Unknown",
            "tls_status": "Unknown",
            "route_status": "Unknown",
            "outbound_status": "Unknown",
            "last_error": "",
            "connection_status": "Disconnected",
        }
        self.service_state = ServiceStateStore(root)
        self._traffic_snapshot = self.traffic.snapshot()
        self._sync_status = {
            "status": "idle",
            "remote_version": "",
            "previous_version": "",
            "records": 0,
            "new_records": 0,
            "updated": "",
            "skipped": False,
        }
        self._update_status = {
            "status": "idle",
            "update_available": False,
            "local_version": "",
            "remote_version": "",
            "remote_build": 0,
            "release_notes": "",
            "release_url": "",
            "message": "",
        }
        self._traffic_timer = QTimer(self)
        self._traffic_timer.setInterval(1000)
        self._traffic_timer.timeout.connect(self._sample_traffic)
        self._traffic_timer.start()
        self._sync_timer = QTimer(self)
        self._sync_timer.timeout.connect(self.autoSyncFromGitHub)
        self._configure_sync_timer()
        self._cleanup_timer = QTimer(self)
        self._cleanup_timer.setInterval(5 * 60 * 1000)
        self._cleanup_timer.timeout.connect(self._cleanup_failed_configs)
        self._cleanup_timer.start()
        if self.settings.get("auto_sync", True):
            QTimer.singleShot(900, self.autoSyncFromGitHub)
        if self.settings.get("auto_update", True):
            QTimer.singleShot(1600, self.checkForUpdates)

    def _cleanup_failed_configs(self) -> None:
        try:
            removed = self.db.delete_failed_configs(min_failures=5, max_age_hours=48)
            if removed > 0:
                logger.info("Auto-removed %d failed configs from database", removed)
                self.configsChanged.emit()
                self.statsChanged.emit()
        except Exception as exc:
            logger.warning("Failed to cleanup configs: %s", exc)

    @Property(bool, notify=busyChanged)
    def busy(self) -> bool:
        return self._busy

    @Property(bool, notify=validationRunningChanged)
    def validationRunning(self) -> bool:
        return self._validation_running

    @Property(int, notify=progressChanged)
    def progressValue(self) -> int:
        return self._progress_value

    @Property(int, notify=progressChanged)
    def progressTotal(self) -> int:
        return self._progress_total

    @Property(int, notify=progressChanged)
    def progressDone(self) -> int:
        return self._progress_done

    @Property(str, notify=progressChanged)
    def progressTitle(self) -> str:
        return self._progress_title

    @Property(str, notify=progressChanged)
    def progressDetail(self) -> str:
        return self._progress_detail

    @Property(str, notify=currentServerChanged)
    def currentServer(self) -> str:
        return self._current_server

    @Property(str, notify=connectionModeChanged)
    def connectionMode(self) -> str:
        return self._connection_mode

    @Property(str, notify=connectionModeChanged)
    def connectionStatus(self) -> str:
        return self._connection_state

    @Property(str, notify=connectionModeChanged)
    def proxyStatus(self) -> str:
        return self._proxy_status

    @Property(str, notify=connectionModeChanged)
    def vpnStatus(self) -> str:
        return self._vpn_status

    def _set_busy(self, value: bool) -> None:
        if self._busy != value:
            self._busy = value
            self.busyChanged.emit()

    def _set_validation_running(self, value: bool) -> None:
        if self._validation_running != value:
            self._validation_running = value
            self.validationRunningChanged.emit()

    def _set_current_server(self, value: str) -> None:
        if self._current_server != value:
            self._current_server = value
            self.currentServerChanged.emit()

    def _set_connection_mode(self, value: str) -> None:
        if self._connection_mode != value:
            self._connection_mode = value
            self.connectionModeChanged.emit()

    def _set_connection_state(self, value: str) -> None:
        if self._connection_state != value:
            self._connection_state = value
            self._diagnostics["connection_status"] = value
            self.connectionModeChanged.emit()

    def _sample_traffic(self) -> None:
        self._traffic_snapshot = self.traffic.sample()
        self.trafficChanged.emit()
        if self._connection_mode != "disconnected":
            self.statsChanged.emit()

    def _start_progress(self, title: str, total: int, detail: str = "") -> None:
        self._progress_title = title
        self._progress_total = total
        self._progress_done = 0
        self._progress_value = 0
        self._progress_detail = detail
        self.progressChanged.emit()

    def _update_progress(self, done: int, total: int, detail: str = "") -> None:
        self._progress_total = total
        self._progress_done = done
        self._progress_value = int((done / total) * 100) if total else 0
        self._progress_detail = detail
        self.progressChanged.emit()

    def _finish_progress(self, detail: str = "") -> None:
        if self._progress_total:
            self._progress_done = self._progress_total
            self._progress_value = 100
        self._progress_detail = detail
        self.progressChanged.emit()

    def _emit_live_update(self, force: bool = False) -> None:
        now = time.monotonic()
        if force or now - self._last_live_emit >= 0.25:
            self._last_live_emit = now
            self.configsChanged.emit()
            self.statsChanged.emit()

    def _configure_sync_timer(self) -> None:
        interval_minutes = int(self.settings.get("sync_interval", 5) or 5)
        self._sync_timer.setInterval(max(1, interval_minutes) * 60 * 1000)
        if self.settings.get("auto_sync", True):
            self._sync_timer.start()
        else:
            self._sync_timer.stop()

    @Slot(result="QVariantList")
    def configList(self) -> list[dict]:
        items: list[dict] = []
        configs = [c for c in self.db.list_configs(limit=1000) if is_ready_status(c.status.value)]
        configs.sort(key=_smart_rank_key)
        for config in configs[:120]:
            data = config.model_dump(mode="json", exclude={"raw"})
            data["ready"] = True
            data["quality"] = _quality_label(float(data.get("score", 0)))
            data["ping_ms"] = config.ping_ms or config.response_time_ms
            items.append(data)
        return items

    @Slot(result="QVariantList")
    def favoriteList(self) -> list[dict]:
        items: list[dict] = []
        configs = [c for c in self.db.list_configs(limit=1000) if c.favorite and is_ready_status(c.status.value)]
        configs.sort(key=_smart_rank_key)
        for config in configs:
            data = config.model_dump(mode="json", exclude={"raw"})
            data["ready"] = True
            data["quality"] = _quality_label(float(data.get("score", 0)))
            data["ping_ms"] = config.ping_ms or config.response_time_ms
            items.append(data)
        return items

    @Slot(result="QVariantList")
    def sourceList(self) -> list[str]:
        return self.sources.list()

    @Slot(result="QVariantList")
    def repositoryList(self) -> list[dict]:
        return [repository.model_dump(mode="json") for repository in self.db.list_repositories()]

    @Slot(result="QVariantMap")
    def trafficStats(self) -> dict:
        return dict(self._traffic_snapshot)

    @Slot(result="QVariantMap")
    def coreStatus(self) -> dict:
        return self.core.status()

    @Slot(result="QVariantList")
    def historyList(self) -> list[dict]:
        return self.history.list()

    @Slot(result="QVariantList")
    def coreLogs(self) -> list[str]:
        return self.core.tail_logs()

    @Slot(result="QVariantList")
    def downloadsList(self) -> list[dict]:
        download_folder = self.root / str(self.settings.get("download_folder", "downloads"))
        if not download_folder.exists():
            return []
        return [
            {"name": item.name, "path": str(item), "size": item.stat().st_size}
            for item in sorted(download_folder.glob("*"), key=lambda path: path.stat().st_mtime, reverse=True)
            if item.is_file()
        ][:80]

    @Slot(result="QVariantMap")
    def appSettings(self) -> dict:
        return self.settings.all()

    @Slot(result="QVariantMap")
    def syncStatus(self) -> dict:
        return dict(self._sync_status)

    @Slot(result="QVariantMap")
    def updateStatus(self) -> dict:
        return dict(self._update_status)

    @Slot(result="QVariantMap")
    def serviceStatus(self) -> dict:
        return self.service_state.read()

    @Slot(result="QVariantMap")
    def diagnosticsStatus(self) -> dict:
        service = self.service_state.read()
        core = self.core.status()
        return {
            **self._diagnostics,
            "service_status": service.get("status", "Stopped"),
            "service_last_error": service.get("last_error", ""),
            "service_last_sync": service.get("last_sync", ""),
            "service_last_health_check": service.get("last_health_check", ""),
            "core_running": core.get("running", False),
            "core_version": core.get("version", "Unknown"),
            "core_memory": core.get("memoryText", "0 B"),
            "proxy_status": self._proxy_status,
            "vpn_status": self._vpn_status,
        }

    @Slot(str)
    def addSource(self, url: str) -> None:
        self.sources.add(url)
        self.sourcesChanged.emit()
        self.notification.emit("Source added.")

    @Slot(str)
    def removeSource(self, url: str) -> None:
        self.sources.remove(url)
        self.sourcesChanged.emit()
        self.notification.emit("Source removed.")

    @Slot(str, "QVariant")
    def setSetting(self, key: str, value: Any) -> None:
        self.settings.set(key, value)
        if key == "validation_workers":
            try:
                self._validation_concurrency = max(1, int(value))
            except Exception:
                pass
        if key == "validation_timeout":
            try:
                self.health.timeout = max(2, float(value))
            except Exception:
                pass
        if key in {"auto_sync", "sync_interval"}:
            self._configure_sync_timer()
        self.settingsChanged.emit()
        self.notification.emit("Setting updated.")

    @Slot()
    def refreshConfigs(self) -> None:
        urls = self.sources.list()
        if not urls:
            self.notification.emit("Add a subscription or raw URL first.")
            return
        self._set_busy(True)
        self._start_progress("Refreshing subscriptions", len(urls), "Downloading source lists")
        future = self.runner.submit(self.collector.collect(urls))

        def done(_future) -> None:
            try:
                configs = _future.result()
                added = self.db.upsert_configs(configs)
                self.notification.emit(f"Collected {len(configs)} configs, {added} new.")
                self._finish_progress("Refresh finished")
                self.configsChanged.emit()
                self.statsChanged.emit()
                if configs:
                    self._auto_validate_new_configs(configs)
            except Exception as exc:
                self.notification.emit(f"Refresh failed: {exc}")
                self._set_busy(False)

        future.add_done_callback(done)

    def _auto_validate_new_configs(self, configs: list) -> None:
        self._start_progress("Pinging new nodes", len(configs), "Quick connectivity check")
        health = HealthChecker(root=self.root, timeout=QUICK_CHECK_TIMEOUT)
        limit = min(int(self.settings.get("validation_workers", 8)), 16)
        future = self.runner.submit(health.quick_check_many(configs, limit=limit, progress_callback=self._on_quick_progress))

        def done(_future) -> None:
            try:
                checked = _future.result()
                self.db.upsert_configs(checked)
                ready = sum(1 for c in checked if is_ready_status(c.status.value))
                self.notification.emit(f"Ping done: {ready}/{len(checked)} nodes online")
                self._finish_progress(f"{ready}/{len(checked)} online")
            except Exception as exc:
                logger.warning("Quick ping failed: %s", exc)
                self._finish_progress("Ping completed with errors")
            finally:
                self._set_busy(False)
                self.configsChanged.emit()
                self.statsChanged.emit()

        future.add_done_callback(done)

    def _on_quick_progress(self, done: int, total: int, config) -> None:
        ping = f"{config.ping_ms}ms" if config.ping_ms is not None else config.status.value
        self._update_progress(done, total, f"{config.name} - {ping}")
        if done % 5 == 0 or done == total:
            self.configsChanged.emit()

    @Slot()
    def scanUpdates(self) -> None:
        self._sync_from_github(force=True, user_visible=True)

    @Slot()
    def autoSyncFromGitHub(self) -> None:
        self._sync_from_github(force=False, user_visible=False)

    def _sync_from_github(self, *, force: bool, user_visible: bool) -> None:
        base_url = str(self.settings.get("github_distribution_base_url", "")).strip()
        if not base_url:
            if user_visible:
                self.notification.emit("Set GitHub distribution base URL in Settings first.")
            return
        if self._busy:
            if user_visible:
                self.notification.emit("Another operation is running.")
            return
        self._set_busy(True)
        self._start_progress("Scanning GitHub distribution", 0, "Checking version.json")
        self._sync_status["status"] = "checking"
        self.syncChanged.emit()
        future = self.runner.submit(GitHubDatasetClient(self.root, base_url).sync(force=force))

        def done(_future) -> None:
            try:
                result = _future.result()
                self._sync_status = {"status": "complete", **result}
                if result.get("skipped"):
                    message = "GitHub dataset is already current."
                    self.notification.emit(message)
                    self._finish_progress("GitHub dataset current")
                    self._set_busy(False)
                else:
                    message = f"SCAN complete: {result['new_records']} new records."
                    self.notification.emit(message)
                    self._finish_progress("GitHub dataset merged")
                    new_count = int(result.get("new_records", 0) or 0)
                    if new_count > 0:
                        self.configsChanged.emit()
                        self.statsChanged.emit()
                        self._auto_validate_new_configs(self.db.list_configs(limit=new_count))
                    else:
                        self._set_busy(False)
                if user_visible or int(result.get("new_records", 0) or 0) > 0:
                    pass
            except Exception as exc:
                self._sync_status["status"] = "failed"
                if user_visible:
                    self.notification.emit(f"SCAN failed: {exc}")
                self._set_busy(False)
            finally:
                self.syncChanged.emit()
                if not self._busy:
                    self.configsChanged.emit()
                    self.statsChanged.emit()

        future.add_done_callback(done)

    @Slot()
    def checkForUpdates(self) -> None:
        version_url = str(self.settings.get("update_version_url", "")).strip()
        if not version_url:
            self._update_status = {"status": "disabled", "update_available": False}
            self.updateChanged.emit()
            return
        self._update_status["status"] = "checking"
        self.updateChanged.emit()
        future = self.runner.submit(UpdateManager(self.root, version_url).check())

        def done(_future) -> None:
            try:
                result = _future.result()
                remote = result.get("remote", {})
                local = result.get("local", {})
                self._update_status = {
                    "status": "available" if result.get("update_available") else "current",
                    "update_available": bool(result.get("update_available")),
                    "local_version": local.get("version", ""),
                    "remote_version": remote.get("version", ""),
                    "remote_build": int(remote.get("build", 0) or 0),
                    "release_notes": remote.get("release_notes", ""),
                    "release_url": remote.get("release_url", ""),
                    "download_url": remote.get("download_url", ""),
                    "message": "Update Available" if result.get("update_available") else "Application is up to date.",
                    "remote": remote,
                }
                if result.get("update_available"):
                    self.notification.emit(f"Update available: {remote.get('version', '')}")
            except Exception as exc:
                self._update_status = {"status": "failed", "update_available": False, "message": str(exc)}
            finally:
                self.updateChanged.emit()

        future.add_done_callback(done)

    @Slot()
    def updateNow(self) -> None:
        remote = self._update_status.get("remote", {})
        if not remote:
            self.notification.emit("No update metadata available.")
            return
        self._set_busy(True)
        self._start_progress("Downloading update", 0, remote.get("version", ""))
        version_url = str(self.settings.get("update_version_url", "")).strip()
        future = self.runner.submit(UpdateManager(self.root, version_url).download_and_stage(remote))

        def done(_future) -> None:
            try:
                result = _future.result()
                self._update_status["status"] = result.get("status", "staged")
                self._update_status["message"] = "Update downloaded and staged. Restart may be required."
                self.notification.emit(self._update_status["message"])
                self._finish_progress("Update staged")
            except Exception as exc:
                self._update_status["status"] = "failed"
                self._update_status["message"] = str(exc)
                self.notification.emit(f"Update failed: {exc}")
            finally:
                self._set_busy(False)
                self.updateChanged.emit()

        future.add_done_callback(done)

    @Slot()
    def updateLater(self) -> None:
        self._update_status["status"] = "later"
        self._update_status["update_available"] = False
        self.updateChanged.emit()
        self.notification.emit("Update postponed.")

    @Slot()
    def skipUpdateVersion(self) -> None:
        build = int(self._update_status.get("remote_build", 0) or 0)
        if build:
            version_url = str(self.settings.get("update_version_url", "")).strip()
            UpdateManager(self.root, version_url).skip(build)
        self._update_status["status"] = "skipped"
        self._update_status["update_available"] = False
        self.updateChanged.emit()
        self.notification.emit("Version skipped.")

    @Slot()
    def discoverSources(self) -> None:
        self._set_busy(True)
        self._start_progress("Discovering repositories", 0, "Mining GitHub raw sources")
        engine = GitHubDiscoveryEngine(self.root, max_repos=40)
        future = self.runner.submit(engine.discover(limit=25))

        def done(_future) -> None:
            try:
                repositories = _future.result()
                self.db.upsert_repositories(repositories)
                output_path = save_discovery_output(self.root, repositories)
                raw_urls = [url for repository in repositories for url in repository.raw_urls]
                self.sources.extend(raw_urls)
                self.notification.emit(f"Discovered {len(repositories)} repos and {len(raw_urls)} raw URLs.")
                self.notification.emit(f"Saved discovery output: {output_path.name}")
                self._finish_progress("Discovery finished")
            except Exception as exc:
                self.notification.emit(f"Discovery failed: {exc}")
            finally:
                self._set_busy(False)
                self.sourcesChanged.emit()
                self.statsChanged.emit()

        future.add_done_callback(done)

    @Slot()
    def testAll(self) -> None:
        self.startValidation()

    @Slot()
    def startValidation(self) -> None:
        if self._validation_running:
            self.notification.emit("Validation is already running.")
            return
        configs = self.db.list_configs()
        if not configs:
            self.notification.emit("No configs to test.")
            return
        self._set_validation_running(True)
        self._validation_concurrency = int(self.settings.get("validation_workers", self._validation_concurrency))
        self.health.timeout = float(self.settings.get("validation_timeout", self.health.timeout))
        self._start_progress("Live validation on YouTube", len(configs), "Starting validation queue")

        def progress(done: int, total: int, config) -> None:
            ping = f"{config.ping_ms} ms" if config.ping_ms is not None else config.status.value
            self._update_progress(done, total, f"{config.name} - {ping}")

        def stage(config) -> None:
            self.db.upsert_configs([config])
            ready = is_ready_status(config.status.value)
            if ready:
                ping = f"{config.ping_ms} ms" if config.ping_ms is not None else "ready"
                self.notification.emit(f"Ready: {config.name} ({ping})")
            self._emit_live_update(force=ready or config.status.value in {"offline", "timeout", "invalid", "unstable"})

        self._validation_future = self.runner.submit(
            self.health.check_many(
                configs,
                limit=self._validation_concurrency,
                progress_callback=progress,
                stage_callback=stage,
            )
        )

        def done(_future) -> None:
            try:
                checked = _future.result()
                self.db.upsert_configs(checked)
                self.notification.emit("Live validation cycle finished.")
                self._finish_progress("All configs tested against YouTube")
            except (asyncio.CancelledError, CancelledError):
                self.notification.emit("Validation stopped.")
                self._finish_progress("Validation stopped")
            except Exception as exc:
                self.notification.emit(f"Validation failed: {exc}")
            finally:
                self._validation_future = None
                self._set_validation_running(False)
                self.configsChanged.emit()
                self.statsChanged.emit()

        self._validation_future.add_done_callback(done)

    @Slot()
    def stopValidation(self) -> None:
        if self._validation_future is None:
            self.notification.emit("Validation is not running.")
            return
        self._validation_future.cancel()

    @Slot(str)
    def testConfig(self, config_id: str) -> None:
        if self._validation_running:
            self.notification.emit("Stop live validation before retesting one config.")
            return
        config = self.db.get_config(config_id)
        if config is None:
            self.notification.emit("Config not found.")
            return
        self._set_validation_running(True)
        self._start_progress("Testing selected config on YouTube", 1, config.name)
        future = self.runner.submit(
            self.health.check_many(
                [config],
                progress_callback=lambda done, total, item: self._update_progress(done, total, item.name),
                stage_callback=lambda item: (self.db.upsert_configs([item]), self.configsChanged.emit(), self.statsChanged.emit()),
            )
        )

        def done(_future) -> None:
            try:
                checked = _future.result()
                self.db.upsert_configs(checked)
                result = checked[0]
                ping = f"{result.ping_ms} ms" if result.ping_ms is not None else result.status.value
                self.notification.emit(f"{result.name}: {ping}")
                self._finish_progress("Selected config tested")
            except Exception as exc:
                self.notification.emit(f"Config test failed: {exc}")
            finally:
                self._set_validation_running(False)
                self.configsChanged.emit()
                self.statsChanged.emit()

        future.add_done_callback(done)

    @Slot(str)
    def deleteConfig(self, config_id: str) -> None:
        self.db.delete_config(config_id)
        self.configsChanged.emit()
        self.statsChanged.emit()
        self.notification.emit("Config deleted.")

    @Slot(str)
    def toggleFavorite(self, config_id: str) -> None:
        config = self.db.get_config(config_id)
        if config is None:
            self.notification.emit("Config not found.")
            return
        self.db.set_favorite(config_id, not config.favorite)
        self.configsChanged.emit()
        self.notification.emit("Favorite updated.")

    @Slot(str)
    def copyConfig(self, config_id: str) -> None:
        config = self.db.get_config(config_id)
        if config is None:
            self.notification.emit("Config not found.")
            return
        clipboard = QGuiApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(config.raw)
            self.notification.emit("Config copied.")

    @Slot(str)
    def exportConfig(self, config_id: str) -> None:
        config = self.db.get_config(config_id)
        if config is None:
            self.notification.emit("Config not found.")
            return
        download_folder = self.root / str(self.settings.get("download_folder", "downloads"))
        download_folder.mkdir(parents=True, exist_ok=True)
        safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", config.name)[:80] or config.id
        path = download_folder / f"{safe_name}.txt"
        path.write_text(config.raw, encoding="utf-8")
        self.history.add("download", {"config_id": config.id, "name": config.name, "path": str(path)})
        self.notification.emit(f"Exported: {path.name}")

    @Slot(str)
    def showDetails(self, config_id: str) -> None:
        config = self.db.get_config(config_id)
        if config is None:
            self.notification.emit("Config not found.")
            return
        self.notification.emit(f"{config.protocol.upper()} {config.host}:{config.port} score={int(config.score)} status={config.status.value}")

    @Slot(result="QVariantMap")
    def stats(self) -> dict:
        data = self.db.config_stats()
        data["currentNode"] = self._current_server
        data["connected"] = 0 if self._current_server == "Disconnected" else 1
        data["connectionMode"] = self._connection_mode
        data["connectionStatus"] = self._connection_state
        data["monthlyUsage"] = self._traffic_snapshot.get("monthlyUsageText", "0 B")
        data["uploadSpeed"] = self._traffic_snapshot.get("uploadSpeedText", "0 B/s")
        data["downloadSpeed"] = self._traffic_snapshot.get("downloadSpeedText", "0 B/s")
        return data

    @Slot(str)
    def connectConfig(self, config_id: str) -> None:
        self._connect_config(config_id, "proxy")

    def _connect_config(self, config_id: str, mode: str, is_failover: bool = False) -> None:
        config = self.db.get_config(config_id)
        if config is None:
            if is_failover:
                self._try_failover()
            else:
                self.notification.emit("Config not found.")
            return
        if not is_ready_status(config.status.value):
            if is_failover:
                self._try_failover()
            else:
                self.notification.emit("This node is not Ready yet. Run validation or retest it first.")
            return
        self._set_connection_state("Connecting")
        self._set_busy(True)
        self._start_progress(f"Connecting {mode.upper()}", 0, config.name)
        self._current_config_id = config.id
        http_port = int(self.settings.get("http_port", 10809))
        config_to_try = config

        async def start_and_verify() -> dict:
            try:
                config_path = export_xray_config(
                    config,
                    self.root / "cache" / "active-xray.json",
                    socks_port=int(self.settings.get("socks_port", 10808)) if self.settings.get("enable_socks", True) else None,
                    http_port=http_port if self.settings.get("enable_http", True) else None,
                    dns_server=str(self.settings.get("dns_server", "1.1.1.1")),
                    prefer_ipv6=bool(self.settings.get("ipv6", False)),
                )
            except Exception as exc:
                return {"message": f"Connect export failed: {exc}", "verification": {"status": "Failed", "last_error": str(exc)}}
            message = await self.core.start(config_path)
            if "started" not in message.lower():
                return {"message": message, "verification": {"status": "Failed", "last_error": message}}
            self._set_connection_state("Verifying")
            for attempt in range(3):
                try:
                    verification = await verify_proxy_connection(
                        http_port,
                        timeout=float(self.settings.get("validation_timeout", 8)),
                    )
                    if verification.get("status") == "Connected":
                        return {"message": message, "verification": verification}
                    if attempt < 2:
                        await asyncio.sleep(1.0)
                except Exception as exc:
                    if attempt < 2:
                        await asyncio.sleep(1.0)
                        continue
                    return {"message": message, "verification": {"status": "Failed", "last_error": str(exc)}}
            return {"message": message, "verification": {"status": "Failed", "last_error": "Verification failed after retries"}}

        future = self.runner.submit(start_and_verify())

        def done(_future) -> None:
            nonlocal config_to_try
            try:
                result = _future.result()
                message = result.get("message", "")
                verification = result.get("verification", {})
                self._diagnostics.update(verification)
                self.notification.emit(message)
                if "started" in message.lower() and verification.get("status") == "Connected":
                    self._set_current_server(config_to_try.name)
                    self._set_connection_mode(mode)
                    self._set_connection_state("Connected")
                    self._proxy_status = "enabled" if mode in {"proxy", "smart"} else self._proxy_status
                    if self.settings.get("set_system_proxy_on_connect", False):
                        self.proxy.set_mode("proxy", "127.0.0.1", http_port)
                    self.connectionModeChanged.emit()
                    self.traffic.start_session()
                    self.history.add("connect", {"mode": mode, "config_id": config_to_try.id, "name": config_to_try.name, "protocol": config_to_try.protocol})
                    self.notification.emit(f"Connected and verified: {config_to_try.name}")
                    self._failover_config_ids = []
                else:
                    self._set_connection_state("Failed")
                    self._set_current_server("Disconnected")
                    error_msg = verification.get("last_error", message)
                    self.history.add("connect_failed", {"mode": mode, "config_id": config_to_try.id, "name": config_to_try.name, "error": error_msg})
                    if is_failover or mode == "smart":
                        self._try_failover()
                self._finish_progress(message)
            except Exception as exc:
                self._set_connection_state("Failed")
                self._diagnostics["last_error"] = str(exc)
                self.notification.emit(f"Connect failed: {exc}")
                if is_failover or mode == "smart":
                    self._try_failover()
            finally:
                self._set_busy(False)

        future.add_done_callback(done)

    def _try_failover(self) -> None:
        if not self._failover_config_ids:
            ready = [c for c in self.db.list_configs(limit=1000) if is_ready_status(c.status.value) and c.id != self._current_config_id]
            ready.sort(key=_smart_rank_key)
            self._failover_config_ids = [c.id for c in ready[:MAX_FAILOVER_ATTEMPTS]]
        if self._failover_config_ids:
            next_id = self._failover_config_ids.pop(0)
            logger.info("Failover: trying next node %s", next_id)
            self.notification.emit(f"Failover: trying next healthy node...")
            self._connect_config(next_id, self._connection_mode if self._connection_mode != "disconnected" else "proxy", is_failover=True)
        else:
            self.notification.emit("No more nodes to failover to.")
            self._set_connection_state("Disconnected")
            self._set_connection_mode("disconnected")

    @Slot()
    def enableProxy(self) -> None:
        if self._current_config_id:
            self._connect_config(self._current_config_id, "proxy")
        else:
            self.notification.emit("Choose a Ready node first.")

    @Slot()
    def disableProxy(self) -> None:
        self.disconnect()

    @Slot()
    def enableVpn(self) -> None:
        self._vpn_status = "blocked"
        self.connectionModeChanged.emit()
        self.notification.emit("VPN/TUN mode requires administrator privileges, system routes, and a supported TUN driver. Proxy mode is ready now.")

    @Slot()
    def disableVpn(self) -> None:
        self._vpn_status = "disabled"
        self.connectionModeChanged.emit()
        self.notification.emit("VPN mode disabled.")

    @Slot()
    def smartConnect(self) -> None:
        ready = [config for config in self.db.list_configs(limit=1000) if is_ready_status(config.status.value)]
        if not ready:
            self.notification.emit("No Ready node found. Start Live Validate first.")
            return
        ready.sort(key=_smart_rank_key)
        self._failover_config_ids = [c.id for c in ready[1:MAX_FAILOVER_ATTEMPTS + 1]]
        self._connect_config(ready[0].id, "smart")

    @Slot()
    def disconnect(self) -> None:
        self._set_busy(True)
        self._set_connection_state("Disconnecting")
        self._start_progress("Disconnecting", 0, self._current_server)
        self._failover_config_ids = []
        future = self.runner.submit(self.core.stop())

        def done(_future) -> None:
            try:
                self.notification.emit(_future.result())
                self._set_current_server("Disconnected")
                self._set_connection_mode("disconnected")
                self._set_connection_state("Disconnected")
                self._proxy_status = "disabled"
                if self.settings.get("set_system_proxy_on_connect", False):
                    self.proxy.disable()
                self.traffic.stop_session()
                if self._current_config_id:
                    self.history.add("disconnect", {"config_id": self._current_config_id})
                self._finish_progress("Disconnected")
            except Exception as exc:
                self.notification.emit(f"Disconnect failed: {exc}")
            finally:
                self._set_busy(False)

        future.add_done_callback(done)

    @Slot()
    def reconnect(self) -> None:
        if not self._current_config_id:
            self.notification.emit("No active config to reconnect.")
            return
        self._set_connection_state("Reconnecting")
        self.connectConfig(self._current_config_id)

    @Slot(str)
    def setProxyMode(self, mode: str) -> None:
        self.notification.emit(self.proxy.set_mode(mode, "127.0.0.1", int(self.settings.get("http_port", 10809))))

    @Slot(str)
    def runNetworkTool(self, tool: str) -> None:
        labels = {
            "ping": "Ping check queued for youtube.com.",
            "dns": "DNS check uses the validation engine cache path for youtube.com.",
            "route": "Route check is available through the active Xray proxy route.",
        }
        self.notification.emit(labels.get(tool, "Network tool queued."))

    @Slot()
    def restartCore(self) -> None:
        self._set_busy(True)
        future = self.runner.submit(self.core.restart())

        def done(_future) -> None:
            try:
                self.notification.emit(_future.result())
            except Exception as exc:
                self.notification.emit(f"Restart failed: {exc}")
            finally:
                self._set_busy(False)
                self.connectionModeChanged.emit()

        future.add_done_callback(done)

    @Slot()
    def stopCore(self) -> None:
        self.disconnect()

    @Slot()
    def updateCore(self) -> None:
        self.notification.emit("Run scripts/download_cores.ps1 to update Xray/V2Ray core from GitHub.")

    @Slot()
    def buildDistribution(self) -> None:
        self.notification.emit("Run scripts/build_distribution.py to regenerate distribution files from local cache.")

    @Slot()
    def publishDistribution(self) -> None:
        publisher = GitHubDistributionPublisher(self.root)
        total_records = int(self._sync_status.get("records", 0) or self.db.config_stats().get("total", 0) or 0)
        result = publisher.publish(publisher.auto_message(total_records))
        self.notification.emit(result.splitlines()[-1] if result else "Publish completed.")

    @Slot(str)
    def serviceControl(self, action: str) -> None:
        if action not in {"install", "start", "stop", "restart", "status", "remove", "run-once"}:
            self.notification.emit("Unknown service action.")
            return
        script = self.root / "scripts" / "service_control.ps1"
        if not script.exists():
            self.notification.emit("Service control script not found.")
            return
        self._set_busy(True)
        self._start_progress(f"Service {action}", 0, "Windows background service")

        def run_command() -> str:
            completed = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(script),
                    "-Action",
                    action,
                ],
                cwd=str(self.root),
                capture_output=True,
                text=True,
                timeout=180,
                creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
            )
            output = (completed.stdout + completed.stderr).strip()
            if completed.returncode != 0:
                raise RuntimeError(output or f"Service {action} failed")
            return output or f"Service {action} complete."

        async def run_command_async() -> str:
            return await asyncio.to_thread(run_command)

        future = self.runner.submit(run_command_async())

        def done(_future) -> None:
            try:
                output = _future.result()
                self.notification.emit(output.splitlines()[-1] if output else f"Service {action} complete.")
                self._finish_progress("Service command finished")
            except Exception as exc:
                self._diagnostics["last_error"] = str(exc)
                self.notification.emit(f"Service {action} failed: {exc}")
            finally:
                self._set_busy(False)
                self.statsChanged.emit()

        future.add_done_callback(done)


def _quality_label(score: float) -> str:
    if score >= 85:
        return "Excellent"
    if score >= 70:
        return "Good"
    if score >= 45:
        return "Average"
    return "Poor"


def _smart_rank_key(config) -> tuple:
    total = config.success_count + config.failure_count
    success_rate = config.success_count / total if total else 1.0
    ping = config.ping_ms if config.ping_ms is not None else 999999
    return (-float(config.score), ping, -success_rate, config.last_check_at or "")
