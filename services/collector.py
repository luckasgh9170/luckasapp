from __future__ import annotations

import asyncio

import httpx

from models.config import ProxyConfig
from services.parser import extract_configs


class ConfigCollector:
    def __init__(self, timeout: float = 12.0) -> None:
        self.timeout = timeout

    async def fetch_source(self, url: str) -> str:
        async with httpx.AsyncClient(follow_redirects=True, timeout=self.timeout) as client:
            response = await client.get(url)
            response.raise_for_status()
            return response.text

    async def collect(self, urls: list[str]) -> list[ProxyConfig]:
        tasks = [self.fetch_source(url) for url in urls if url.strip()]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        configs: list[ProxyConfig] = []
        seen: set[str] = set()
        for result in results:
            if isinstance(result, Exception):
                continue
            for config in extract_configs(result):
                if config.id not in seen:
                    seen.add(config.id)
                    configs.append(config)
        return configs
