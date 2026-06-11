from __future__ import annotations

import asyncio

from models.config import ProxyConfig
from services.api_client import ApiClient, RetryPolicy
from services.parser import extract_configs


class ConfigCollector:
    def __init__(self, root=None, timeout: float = 12.0) -> None:
        from pathlib import Path
        self.root = Path(root) if root is not None else Path.cwd()
        self.timeout = timeout

    async def collect(self, urls: list[str]) -> list[ProxyConfig]:
        async with ApiClient(self.root, timeout=self.timeout, retry=RetryPolicy(attempts=3)) as client:
            tasks = [client.get_text(url) for url in urls if url.strip()]
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
