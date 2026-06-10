from __future__ import annotations

import asyncio
import socket
import time
from typing import Any

import httpx


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

    try:
        async with httpx.AsyncClient(
            proxy=f"http://127.0.0.1:{http_port}",
            timeout=httpx.Timeout(timeout),
            follow_redirects=False,
        ) as client:
            response = await client.get("https://www.youtube.com/generate_204")
        elapsed = int((time.perf_counter() - started) * 1000)
        result["response_time_ms"] = elapsed
        if response.status_code < 500:
            result["tls_status"] = "OK"
            result["route_status"] = "OK"
            result["outbound_status"] = f"HTTP {response.status_code}"
            result["status"] = "Connected"
        else:
            result["tls_status"] = "Failed"
            result["route_status"] = "Failed"
            result["outbound_status"] = f"HTTP {response.status_code}"
            result["status"] = "Failed"
            result["last_error"] = f"Outbound returned HTTP {response.status_code}"
    except Exception as exc:
        result["tls_status"] = "Failed"
        result["route_status"] = "Failed"
        result["outbound_status"] = "Failed"
        result["status"] = "Failed"
        result["last_error"] = f"Verification failed: {exc.__class__.__name__}"
    return result
