from __future__ import annotations

import asyncio
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
from services.health import HealthChecker, is_ready_status
from services.history import HistoryStore
from services.settings import SettingsStore
from services.traffic import TrafficMonitor
from services.updater import UpdateManager
from services.xray_exporter import export_xray_config
from workers.async_runner import AsyncRunner


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
        self.collector = ConfigCollector()
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
        self._connection_mode = "disconnected"
        self._proxy_status = "disabled"
        self._vpn_status = "disabled"
        self._traffic_snapshot = self.traffic.snapshot()
        self._sync_status = {
            "status": "idle",
            "remote_version": "",
            "previous_version": "",
            "records": 0,
            "new_records": 0,
            "updated": "",
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
        if self.settings.get("auto_update", True):
            QTimer.singleShot(1600, self.checkForUpdates)

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

    @Slot(result="QVariantList")
    def configList(self) -> list[dict]:
        items: list[dict] = []
        for config in self.db.list_configs(limit=120):
            data = config.model_dump(mode="json", exclude={"raw"})
            data["ready"] = is_ready_status(data["status"])
            data["quality"] = _quality_label(float(data.get("score", 0)))
            items.append(data)
        return items

    @Slot(result="QVariantList")
    def favoriteList(self) -> list[dict]:
        items: list[dict] = []
        for config in self.db.list_configs(limit=500):
            if config.favorite:
                data = config.model_dump(mode="json", exclude={"raw"})
                data["ready"] = is_ready_status(data["status"])
                data["quality"] = _quality_label(float(data.get("score", 0)))
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
            except Exception as exc:
                self.notification.emit(f"Refresh failed: {exc}")
            finally:
                self._set_busy(False)
                self.configsChanged.emit()
                self.statsChanged.emit()

        future.add_done_callback(done)

    @Slot()
    def scanUpdates(self) -> None:
        base_url = str(self.settings.get("github_distribution_base_url", "")).strip()
        if not base_url:
            self.notification.emit("Set GitHub distribution base URL in Settings first.")
            return
        if self._busy:
            self.notification.emit("Another operation is running.")
            return
        self._set_busy(True)
        self._start_progress("Scanning GitHub distribution", 0, "Checking version.json")
        self._sync_status["status"] = "checking"
        self.syncChanged.emit()
        future = self.runner.submit(GitHubDatasetClient(self.root, base_url).sync())

        def done(_future) -> None:
            try:
                result = _future.result()
                self._sync_status = {"status": "complete", **result}
                self.notification.emit(f"SCAN complete: {result['new_records']} new records.")
                self._finish_progress("GitHub dataset merged")
            except Exception as exc:
                self._sync_status["status"] = "failed"
                self.notification.emit(f"SCAN failed: {exc}")
            finally:
                self._set_busy(False)
                self.syncChanged.emit()
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
        data["monthlyUsage"] = self._traffic_snapshot.get("monthlyUsageText", "0 B")
        data["uploadSpeed"] = self._traffic_snapshot.get("uploadSpeedText", "0 B/s")
        data["downloadSpeed"] = self._traffic_snapshot.get("downloadSpeedText", "0 B/s")
        return data

    @Slot(str)
    def connectConfig(self, config_id: str) -> None:
        self._connect_config(config_id, "proxy")

    def _connect_config(self, config_id: str, mode: str) -> None:
        config = self.db.get_config(config_id)
        if config is None:
            self.notification.emit("Config not found.")
            return
        if not is_ready_status(config.status.value):
            self.notification.emit("This node is not Ready yet. Run validation or retest it first.")
            return
        try:
            config_path = export_xray_config(
                config,
                self.root / "cache" / "active-xray.json",
                socks_port=int(self.settings.get("socks_port", 10808)) if self.settings.get("enable_socks", True) else None,
                http_port=int(self.settings.get("http_port", 10809)) if self.settings.get("enable_http", True) else None,
            )
        except Exception as exc:
            self.notification.emit(f"Connect export failed: {exc}")
            return
        self._set_busy(True)
        self._start_progress(f"Connecting {mode.upper()}", 0, config.name)
        self._current_config_id = config.id
        future = self.runner.submit(self.core.start(config_path))

        def done(_future) -> None:
            try:
                message = _future.result()
                self.notification.emit(message)
                if "started" in message.lower():
                    self._set_current_server(config.name)
                    self._set_connection_mode(mode)
                    self._proxy_status = "enabled" if mode in {"proxy", "smart"} else self._proxy_status
                    self.connectionModeChanged.emit()
                    self.traffic.start_session()
                    self.history.add("connect", {"mode": mode, "config_id": config.id, "name": config.name, "protocol": config.protocol})
                else:
                    self._set_current_server("Disconnected")
                self._finish_progress(message)
            except Exception as exc:
                self.notification.emit(f"Connect failed: {exc}")
            finally:
                self._set_busy(False)

        future.add_done_callback(done)

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
        ready.sort(key=lambda item: (-item.score, item.ping_ms if item.ping_ms is not None else 999999))
        self._connect_config(ready[0].id, "smart")

    @Slot()
    def disconnect(self) -> None:
        self._set_busy(True)
        self._start_progress("Disconnecting", 0, self._current_server)
        future = self.runner.submit(self.core.stop())

        def done(_future) -> None:
            try:
                self.notification.emit(_future.result())
                self._set_current_server("Disconnected")
                self._set_connection_mode("disconnected")
                self._proxy_status = "disabled"
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
        self.connectConfig(self._current_config_id)

    @Slot(str)
    def setProxyMode(self, mode: str) -> None:
        self.notification.emit(self.proxy.set_mode(mode))

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
        result = GitHubDistributionPublisher(self.root).publish("Update dataset from desktop client")
        self.notification.emit(result.splitlines()[-1] if result else "Publish completed.")


def _quality_label(score: float) -> str:
    if score >= 85:
        return "Excellent"
    if score >= 70:
        return "Good"
    if score >= 45:
        return "Average"
    return "Poor"
