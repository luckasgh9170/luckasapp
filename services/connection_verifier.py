from __future__ import annotations

import asyncio
import logging
import socket
import time
from typing import Any

import httpx

logger = logging.getLogger(__name__)

VERIFICATION_RETRIES = 2
VERIFICATION_TARGETS = (
    "https://www.youtube.com/generate_204",
    "https://youtube.com/generate_204",
    "https://www.google.com/generate_204",
)


async def verify_proxy_connection(http_port: int, timeout: float = 8.0) -> dict[str, Any]:
    started = time.perf_counter()
    result: dict[str, Any] = {
        "status": "Verifying",
        "dns_status": "Checking",
        "tls_status": "Checking",
        "route_status": "Checking",
        "outbound_status": "Checking",
        "response_time_ms": 0,
        "last_error": "",
    }
    try:
        await asyncio.wait_for(asyncio.to_thread(socket.getaddrinfo, "youtube.com", 443), timeout=min(timeout, 4))
        result["dns_status"] = "OK"
    except Exception as exc:
        result["dns_status"] = "Failed"
        result["last_error"] = f"DNS failed: {exc.__class__.__name__}"
        result["status"] = "Failed"
        return result

    last_error: Exception | None = None
    limits = httpx.Limits(max_keepalive_connections=4, max_connections=8, keepalive_expiry=15)

    for attempt in range(VERIFICATION_RETRIES + 1):
        try:
            async with httpx.AsyncClient(
                proxy=f"http://127.0.0.1:{http_port}",
                timeout=httpx.Timeout(timeout),
                follow_redirects=False,
                limits=limits,
            ) as client:
                response = None
                for target in VERIFICATION_TARGETS:
                    try:
                        response = await client.get(target)
                        if response.status_code < 500:
                            break
                    except Exception:
                        continue
                elapsed = int((time.perf_counter() - started) * 1000)
                result["response_time_ms"] = elapsed
                if response is not None and response.status_code < 500:
                    result["tls_status"] = "OK"
                    result["route_status"] = "OK"
                    result["outbound_status"] = f"HTTP {response.status_code}"
                    result["status"] = "Connected"
                    result["last_error"] = ""
                    return result
                elif response is not None:
                    result["tls_status"] = "Failed"
                    result["route_status"] = "Failed"
                    result["outbound_status"] = f"HTTP {response.status_code}"
                    result["status"] = "Failed"
                    result["last_error"] = f"Outbound returned HTTP {response.status_code}"
                    return result
        except (httpx.ProxyError, httpx.RemoteProtocolError, httpx.ConnectTimeout, httpx.ReadTimeout) as exc:
            last_error = exc
            logger.debug("Verification attempt %d/%d failed: %s", attempt + 1, VERIFICATION_RETRIES + 1, exc)
            if attempt < VERIFICATION_RETRIES:
                await asyncio.sleep(1.0)
                continue
        except Exception as exc:
            last_error = exc
            logger.debug("Verification attempt %d/%d failed: %s", attempt + 1, VERIFICATION_RETRIES + 1, exc)
            if attempt < VERIFICATION_RETRIES:
                await asyncio.sleep(1.0)
                continue
        break

    result["tls_status"] = "Failed"
    result["route_status"] = "Failed"
    result["outbound_status"] = "Failed"
    result["status"] = "Failed"
    exc_name = last_error.__class__.__name__ if last_error else "Unknown"
    result["last_error"] = f"Verification failed: {exc_name}"
    return result
