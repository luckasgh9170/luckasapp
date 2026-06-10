from __future__ import annotations

from pathlib import Path

import httpx
import orjson

from database.db import Database
from models.dataset import DatasetRecord
from services.dataset import dataset_record_to_config
from services.history import HistoryStore


class GitHubDatasetClient:
    def __init__(self, root: Path, base_url: str) -> None:
        self.root = root
        self.base_url = base_url.rstrip("/")
        self.version_cache = root / "cache" / "remote_dataset_version.json"

    async def sync(self) -> dict:
        if not self.base_url:
            raise RuntimeError("Set github_distribution_base_url in Settings first.")
        async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
            version_response = await client.get(f"{self.base_url}/version.json")
            version_response.raise_for_status()
            version = version_response.json()
            local_version = self._local_version()
            latest_response = await client.get(f"{self.base_url}/data/latest/latest.json")
            latest_response.raise_for_status()
            records = [DatasetRecord(**item) for item in latest_response.json()]
        configs = [dataset_record_to_config(record) for record in records]
        added = Database(self.root).upsert_configs(configs)
        self.version_cache.write_bytes(orjson.dumps(version, option=orjson.OPT_INDENT_2))
        HistoryStore(self.root).add(
            "sync",
            {
                "remote_version": version.get("version", ""),
                "previous_version": local_version.get("version", ""),
                "records": len(records),
                "new_records": added,
            },
        )
        return {
            "remote_version": version.get("version", ""),
            "previous_version": local_version.get("version", ""),
            "records": len(records),
            "new_records": added,
            "updated": version.get("updated", ""),
        }

    def _local_version(self) -> dict:
        if not self.version_cache.exists():
            return {}
        try:
            return orjson.loads(self.version_cache.read_bytes())
        except Exception:
            return {}
