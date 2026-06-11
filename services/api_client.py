from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import orjson


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class RetryPolicy:
    attempts: int = 3
    base_delay: float = 0.4
    max_delay: float = 3.0


class CircuitBreaker:
    def __init__(self, failure_threshold: int = 5, reset_after_seconds: int = 60) -> None:
        self.failure_threshold = failure_threshold
        self.reset_after = timedelta(seconds=reset_after_seconds)
        self.failures = 0
        self.opened_at: datetime | None = None

    def before_request(self) -> None:
        if self.opened_at is None:
            return
        if datetime.now(UTC) - self.opened_at >= self.reset_after:
            self.failures = 0
            self.opened_at = None
            return
        raise RuntimeError("Circuit breaker is open")

    def success(self) -> None:
        self.failures = 0
        self.opened_at = None

    def failure(self) -> None:
        self.failures += 1
        if self.failures >= self.failure_threshold:
            self.opened_at = datetime.now(UTC)


class JsonlNetworkLogger:
    def __init__(self, root: Path) -> None:
        self.path = root / "logs" / "network.jsonl"
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def write(self, event: str, **fields: Any) -> None:
        payload = {"time": _now(), "event": event, **fields}
        with self.path.open("ab") as handle:
            handle.write(orjson.dumps(payload))
            handle.write(b"\n")


class ApiClient:
    def __init__(
        self,
        root: Path,
        *,
        timeout: float = 20.0,
        retry: RetryPolicy | None = None,
        circuit_breaker: CircuitBreaker | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.root = root
        self.retry = retry or RetryPolicy()
        self.breaker = circuit_breaker or CircuitBreaker()
        self.logger = JsonlNetworkLogger(root)
        self.client = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout),
            follow_redirects=True,
            headers=headers,
            limits=httpx.Limits(max_connections=32, max_keepalive_connections=12, keepalive_expiry=30),
        )

    async def close(self) -> None:
        await self.client.aclose()

    async def get(self, url: str) -> httpx.Response:
        last_error: Exception | None = None
        for attempt in range(1, self.retry.attempts + 1):
            try:
                self.breaker.before_request()
                response = await self.client.get(url)
                response.raise_for_status()
                self.breaker.success()
                self.logger.write("request_ok", method="GET", url=url, status=response.status_code, attempt=attempt)
                return response
            except (httpx.TimeoutException, httpx.NetworkError, httpx.HTTPStatusError, RuntimeError) as exc:
                last_error = exc
                status = exc.response.status_code if isinstance(exc, httpx.HTTPStatusError) else 0
                retryable = status in {0, 408, 429, 500, 502, 503, 504}
                self.breaker.failure()
                self.logger.write(
                    "request_failed",
                    method="GET",
                    url=url,
                    status=status,
                    attempt=attempt,
                    error=exc.__class__.__name__,
                    retryable=retryable,
                )
                if attempt >= self.retry.attempts or not retryable:
                    break
                await asyncio.sleep(min(self.retry.max_delay, self.retry.base_delay * (2 ** (attempt - 1))))
        raise RuntimeError(f"GET failed for {url}: {last_error}") from last_error

    async def get_json(self, url: str) -> Any:
        response = await self.get(url)
        return response.json()

    async def get_text(self, url: str) -> str:
        response = await self.get(url)
        return response.text

    async def get_bytes(self, url: str) -> bytes:
        response = await self.get(url)
        return response.content

    async def __aenter__(self) -> "ApiClient":
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.close()
