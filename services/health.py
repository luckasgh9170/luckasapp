from __future__ import annotations

import asyncio
import base64
import logging
import socket
import ssl
import subprocess
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import httpx
import orjson

from models.config import ConfigStatus, ProxyConfig
from services.xray_exporter import export_xray_config

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[int, int, ProxyConfig], None]
StageCallback = Callable[[ProxyConfig], None]
CORE_EXPORT_PROTOCOLS = {"vmess", "vless", "trojan", "shadowsocks"}
READY_STATUSES = {ConfigStatus.HEALTHY, ConfigStatus.WORKING, ConfigStatus.SLOW, ConfigStatus.ONLINE}
FAILED_STATUSES = {ConfigStatus.OFFLINE, ConfigStatus.TIMEOUT, ConfigStatus.INVALID, ConfigStatus.UNSTABLE}
YOUTUBE_TARGETS = (
    "https://youtube.com/generate_204",
    "https://www.youtube.com/generate_204",
)
QUICK_CHECK_TIMEOUT = 6
SSL_ERROR_RETRIES = 2


class HealthChecker:
    def __init__(
        self,
        root: Path | None = None,
        timeout: float = 8.0,
        target_urls: tuple[str, ...] = YOUTUBE_TARGETS,
    ) -> None:
        self.root = root
        self.timeout = timeout
        self.target_urls = target_urls
        self._http_client: httpx.AsyncClient | None = None

    def _get_http_client(self) -> httpx.AsyncClient:
        if self._http_client is None or self._http_client.is_closed:
            limits = httpx.Limits(max_keepalive_connections=8, max_connections=32, keepalive_expiry=30)
            self._http_client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.timeout),
                follow_redirects=False,
                limits=limits,
            )
        return self._http_client

    async def quick_check(self, config: ProxyConfig) -> ProxyConfig:
        config.last_check_at = _utc_now()
        if not self._validate_format(config):
            config.status = ConfigStatus.INVALID
            config.status_detail = "Invalid URI or missing required fields"
            config.score = 0
            return config
        if config.protocol not in CORE_EXPORT_PROTOCOLS:
            config.status = ConfigStatus.UNKNOWN
            config.status_detail = f"Protocol {config.protocol} not fully testable without core"
            return config
        if not await self._check_dns(config.host):
            config.status = ConfigStatus.OFFLINE
            config.status_detail = "DNS resolution failed"
            config.failure_count += 1
            config.score = score_config(config)
            return config
        connection_time = await self._tcp_time(config.host, config.port)
        config.connection_time_ms = connection_time
        if connection_time is None:
            config.status = ConfigStatus.TIMEOUT
            config.status_detail = "TCP connection timeout"
            config.failure_count += 1
            config.score = score_config(config)
            return config
        config.ping_ms = connection_time
        security, sni = _security_hint(config)
        handshake = None
        if security in {"tls", "reality"}:
            handshake = await self._tls_with_retry(config.host, config.port, sni or config.host)
            if handshake is not None:
                config.handshake_time_ms = handshake
        if connection_time <= 500:
            config.status = ConfigStatus.ONLINE
        elif connection_time <= 2000:
            config.status = ConfigStatus.ONLINE
        else:
            config.status = ConfigStatus.SLOW
        config.status_detail = f"TCP {connection_time}ms" + (f" TLS {handshake}ms" if handshake else "")
        config.success_count += 1
        config.score = score_config(config)
        return config

    async def quick_check_many(
        self,
        configs: list[ProxyConfig],
        limit: int = 8,
        progress_callback: ProgressCallback | None = None,
    ) -> list[ProxyConfig]:
        sem = asyncio.Semaphore(limit)
        async def check_one(config: ProxyConfig) -> ProxyConfig:
            async with sem:
                return await self.quick_check(config)
        tasks = [check_one(c) for c in configs]
        results: list[ProxyConfig] = []
        for i, task in enumerate(asyncio.as_completed(tasks)):
            checked = await task
            results.append(checked)
            if progress_callback:
                progress_callback(i + 1, len(configs), checked)
        return results

    async def check(self, config: ProxyConfig, stage_callback: StageCallback | None = None) -> ProxyConfig:
        config.last_check_at = _utc_now()
        self._stage(config, ConfigStatus.TESTING, "Testing URI format", stage_callback)
        if not self._validate_format(config):
            self._finish(config, ConfigStatus.INVALID, "Invalid URI or missing required fields", stage_callback)
            return config

        if config.protocol not in CORE_EXPORT_PROTOCOLS:
            self._finish(
                config,
                ConfigStatus.INVALID,
                f"{config.protocol} is parsed but not supported by Xray/V2Ray exporter yet",
                stage_callback,
            )
            return config

        self._stage(config, ConfigStatus.TESTING, "Checking DNS", stage_callback)
        if not await self._check_dns(config.host):
            self._finish(config, ConfigStatus.OFFLINE, "DNS resolution failed", stage_callback)
            return config

        self._stage(config, ConfigStatus.TESTING, "Checking TCP connectivity", stage_callback)
        connection_time = await self._tcp_time(config.host, config.port)
        config.connection_time_ms = connection_time
        if connection_time is None:
            self._finish(config, ConfigStatus.TIMEOUT, "TCP connection timeout", stage_callback)
            return config

        security, sni = _security_hint(config)
        if security in {"tls", "reality"}:
            self._stage(config, ConfigStatus.TESTING, "Checking TLS/Reality compatibility", stage_callback)
            tls_time = await self._tls_with_retry(config.host, config.port, sni or config.host)
            if tls_time is not None:
                config.handshake_time_ms = tls_time

        self._stage(config, ConfigStatus.TESTING, "Launching isolated Xray test instance", stage_callback)
        result = await self._check_youtube_via_core(config, stage_callback)
        self._finish(result, result.status, result.status_detail, stage_callback)
        return result

    async def _tls_with_retry(self, host: str, port: int, server_hostname: str) -> int | None:
        for attempt in range(SSL_ERROR_RETRIES + 1):
            tls_time = await self._tls_time(host, port, server_hostname)
            if tls_time is not None:
                return tls_time
            if attempt < SSL_ERROR_RETRIES:
                logger.debug("TLS handshake failed for %s, retry %d/%d", host, attempt + 1, SSL_ERROR_RETRIES)
                await asyncio.sleep(0.5)
        return None

    async def _check_youtube_via_core(
        self,
        config: ProxyConfig,
        stage_callback: StageCallback | None,
    ) -> ProxyConfig:
        assert self.root is not None
        core_path = self._discover_core()
        if core_path is None:
            config.status = ConfigStatus.OFFLINE
            config.status_detail = "Core binary not found"
            return config

        http_port = _free_port()
        config_path = self.root / "cache" / "health-tests" / f"{config.id}-{http_port}.json"
        process = None
        started_at = time.perf_counter()
        try:
            export_xray_config(config, config_path, socks_port=None, http_port=http_port, loglevel="error")
            process = await asyncio.create_subprocess_exec(
                str(core_path),
                "run",
                "-config",
                str(config_path),
                cwd=str(self.root),
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
            )
            ready = await self._wait_for_port(http_port)
            config.handshake_time_ms = int((time.perf_counter() - started_at) * 1000)
            if not ready:
                config.status = ConfigStatus.TIMEOUT
                config.status_detail = "Core inbound did not become ready"
                return config

            self._stage(config, ConfigStatus.TESTING, "Checking website reachability", stage_callback)
            status_codes: list[int] = []
            response_times: list[int] = []
            proxy_url = f"http://127.0.0.1:{http_port}"
            limits = httpx.Limits(max_keepalive_connections=4, max_connections=8)
            async with httpx.AsyncClient(
                proxy=proxy_url,
                timeout=httpx.Timeout(self.timeout),
                follow_redirects=False,
                limits=limits,
            ) as client:
                for target_url in self.target_urls:
                    self._stage(config, ConfigStatus.TESTING, f"Checking {target_url}", stage_callback)
                    for attempt in range(2):
                        try:
                            request_start = time.perf_counter()
                            response = await client.get(target_url)
                            response_times.append(int((time.perf_counter() - request_start) * 1000))
                            status_codes.append(response.status_code)
                            break
                        except (httpx.RemoteProtocolError, httpx.LocalProtocolError, httpx.ReadTimeout) as exc:
                            if attempt == 0:
                                logger.debug("Retry %s for %s: %s", target_url, config.name, exc)
                                await asyncio.sleep(0.3)
                                continue
                            raise

            good_statuses = [code for code in status_codes if code < 500]
            if response_times:
                config.response_time_ms = int(sum(response_times) / len(response_times))
                config.ping_ms = config.response_time_ms
            if len(good_statuses) == len(self.target_urls):
                config.status = _classify_ready(config.response_time_ms or 0)
                config.status_detail = f"Success: {', '.join(str(code) for code in status_codes)}"
            elif good_statuses:
                config.status = ConfigStatus.UNSTABLE
                config.status_detail = f"Partial reachability: {', '.join(str(code) for code in status_codes)}"
            else:
                config.status = ConfigStatus.OFFLINE
                config.status_detail = f"Website failed: {', '.join(str(code) for code in status_codes)}"
        except TimeoutError:
            config.status = ConfigStatus.TIMEOUT
            config.status_detail = "Website request timeout"
        except asyncio.CancelledError:
            config.status = ConfigStatus.UNKNOWN
            config.status_detail = "Validation cancelled"
            raise
        except Exception as exc:
            config.status = ConfigStatus.OFFLINE
            config.status_detail = f"Validation failed: {exc.__class__.__name__}"
            logger.debug("Health check error for %s: %s", config.name, exc)
        finally:
            if process:
                await _terminate_process_tree(process)
            try:
                config_path.unlink(missing_ok=True)
            except Exception:
                pass
        return config

    async def _check_dns(self, host: str) -> bool:
        try:
            await asyncio.wait_for(
                asyncio.to_thread(socket.getaddrinfo, host, None),
                timeout=min(self.timeout, 4),
            )
            return True
        except Exception:
            return False

    async def _tcp_time(self, host: str, port: int) -> int | None:
        start = time.perf_counter()
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(host, port),
                timeout=min(self.timeout, 4),
            )
            writer.close()
            await writer.wait_closed()
            return int((time.perf_counter() - start) * 1000)
        except Exception:
            return None

    async def _tls_time(self, host: str, port: int, server_hostname: str) -> int | None:
        context = ssl.create_default_context()
        start = time.perf_counter()
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(host, port, ssl=context, server_hostname=server_hostname),
                timeout=min(self.timeout, 5),
            )
            writer.close()
            await writer.wait_closed()
            return int((time.perf_counter() - start) * 1000)
        except Exception:
            return None

    async def _wait_for_port(self, port: int) -> bool:
        deadline = time.perf_counter() + 4
        while time.perf_counter() < deadline:
            try:
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection("127.0.0.1", port),
                    timeout=0.25,
                )
                writer.close()
                await writer.wait_closed()
                return True
            except Exception:
                await asyncio.sleep(0.1)
        return False

    def _discover_core(self) -> Path | None:
        if self.root is None:
            return None
        for name in ("xray.exe", "v2ray.exe", "xray", "v2ray"):
            candidate = self.root / "core" / "bin" / name
            if candidate.exists():
                return candidate
        return None

    def _validate_format(self, config: ProxyConfig) -> bool:
        return bool(config.raw and config.protocol and config.host and config.port > 0)

    def _stage(
        self,
        config: ProxyConfig,
        status: ConfigStatus,
        detail: str,
        stage_callback: StageCallback | None,
    ) -> None:
        config.status = status
        config.status_detail = detail
        config.last_check_at = _utc_now()
        if stage_callback:
            stage_callback(config)

    def _finish(
        self,
        config: ProxyConfig,
        status: ConfigStatus,
        detail: str,
        stage_callback: StageCallback | None,
    ) -> None:
        config.status = status
        config.status_detail = detail
        config.last_check_at = _utc_now()
        if status in READY_STATUSES:
            config.success_count += 1
        elif status in FAILED_STATUSES:
            config.failure_count += 1
        config.score = score_config(config)
        if stage_callback:
            stage_callback(config)

    def shutdown(self) -> None:
        if self._http_client and not self._http_client.is_closed:
            import asyncio
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    loop.create_task(self._http_client.aclose())
            except Exception:
                pass

    async def check_many(
        self,
        configs: list[ProxyConfig],
        limit: int = 4,
        progress_callback: ProgressCallback | None = None,
        stage_callback: StageCallback | None = None,
    ) -> list[ProxyConfig]:
        queue: asyncio.Queue[ProxyConfig] = asyncio.Queue()
        lock = asyncio.Lock()
        total = len(configs)
        done = 0
        results: list[ProxyConfig] = []
        for config in configs:
            queue.put_nowait(config)

        async def worker() -> None:
            nonlocal done
            while True:
                config = await queue.get()
                try:
                    checked = await self.check(config, stage_callback=stage_callback)
                    async with lock:
                        results.append(checked)
                        done += 1
                        if progress_callback:
                            progress_callback(done, total, checked)
                finally:
                    queue.task_done()

        workers = [asyncio.create_task(worker()) for _ in range(min(max(limit, 1), total or 1))]
        try:
            await queue.join()
        finally:
            for task in workers:
                task.cancel()
            await asyncio.gather(*workers, return_exceptions=True)
        return results


def score_config(config: ProxyConfig) -> float:
    if config.status not in READY_STATUSES:
        return 0
    latency = config.ping_ms if config.ping_ms is not None else 5000
    handshake = config.handshake_time_ms if config.handshake_time_ms is not None else 3000
    total_checks = config.success_count + config.failure_count
    success_rate = config.success_count / total_checks if total_checks else 1.0
    latency_score = max(0, 45 - min(latency, 3000) / 3000 * 45)
    stability_score = success_rate * 30
    handshake_score = max(0, 15 - min(handshake, 2000) / 2000 * 15)
    status_bonus = 10 if config.status == ConfigStatus.HEALTHY else 5 if config.status == ConfigStatus.WORKING else 2
    return round(min(100, latency_score + stability_score + handshake_score + status_bonus), 2)


def is_ready_status(status: str) -> bool:
    try:
        return ConfigStatus(status) in READY_STATUSES
    except ValueError:
        return False


def _classify_ready(response_time_ms: int) -> ConfigStatus:
    if response_time_ms <= 800:
        return ConfigStatus.HEALTHY
    if response_time_ms <= 2000:
        return ConfigStatus.WORKING
    return ConfigStatus.SLOW


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _security_hint(config: ProxyConfig) -> tuple[str, str]:
    try:
        if config.protocol == "vmess":
            payload = config.raw.split("://", 1)[1]
            padded = payload + "=" * (-len(payload) % 4)
            data = orjson.loads(base64.urlsafe_b64decode(padded))
            return str(data.get("tls", "")).lower(), str(data.get("sni") or data.get("host") or "")
        parsed = urlparse(config.raw)
        query = parse_qs(parsed.query)
        return query.get("security", [""])[0].lower(), query.get("sni", query.get("host", [""]))[0]
    except Exception:
        return "", ""


async def _terminate_process_tree(process: asyncio.subprocess.Process) -> None:
    if process.returncode is not None:
        return
    try:
        await asyncio.to_thread(
            subprocess.run,
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        await asyncio.wait_for(process.wait(), timeout=2)
    except Exception:
        if process.returncode is None:
            process.kill()
            try:
                await asyncio.wait_for(process.wait(), timeout=2)
            except Exception:
                pass
