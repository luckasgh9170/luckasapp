from __future__ import annotations

from pathlib import Path
from typing import Any

import orjson

from database.db import Database
from models.dataset import DatasetRecord
from services.api_client import ApiClient, RetryPolicy
from services.dataset import dataset_record_to_config
from services.history import HistoryStore


class GitHubDatasetClient:
    def __init__(self, root: Path, base_url: str) -> None:
        self.root = root
        self.base_url = base_url.rstrip("/")
        self.version_cache = root / "cache" / "remote_dataset_version.json"
        self.index_cache = root / "cache" / "remote_dataset_index.json"

    async def sync(self, force: bool = True) -> dict:
        if not self.base_url:
            raise RuntimeError("Set github_distribution_base_url in Settings first.")
        async with ApiClient(self.root, timeout=20, retry=RetryPolicy(attempts=4)) as client:
            version = await client.get_json(f"{self.base_url}/version.json")
            local_version = self._local_version()
            if not force and self._same_version(local_version, version) and self.index_cache.exists():
                return {
                    "remote_version": version.get("version", ""),
                    "previous_version": local_version.get("version", ""),
                    "records": int(version.get("records", version.get("total_items", 0)) or 0),
                    "new_records": 0,
                    "modified_records": 0,
                    "removed_records": 0,
                    "updated": version.get("updated", ""),
                    "skipped": True,
                }
            records = await self._fetch_records(client)
        configs = [dataset_record_to_config(record) for record in records]
        diff = self._diff_records(records)
        db = Database(self.root)
        added = db.upsert_configs(configs)
        removed = db.mark_remote_removed(set(diff["removed_ids"]))
        _atomic_write_json(self.version_cache, version)
        _atomic_write_json(self.index_cache, self._build_index(records, version))
        HistoryStore(self.root).add(
            "sync",
            {
                "remote_version": version.get("version", ""),
                "previous_version": local_version.get("version", ""),
                "records": len(records),
                "new_records": added,
                "modified_records": diff["modified_records"],
                "removed_records": removed,
            },
        )
        return {
            "remote_version": version.get("version", ""),
            "previous_version": local_version.get("version", ""),
            "records": len(records),
            "new_records": added,
            "modified_records": diff["modified_records"],
            "removed_records": removed,
            "updated": version.get("updated", ""),
            "skipped": False,
        }

    async def check_version(self) -> dict:
        if not self.base_url:
            raise RuntimeError("Set github_distribution_base_url in Settings first.")
        async with ApiClient(self.root, timeout=20, retry=RetryPolicy(attempts=3)) as client:
            remote = await client.get_json(f"{self.base_url}/version.json")
        local = self._local_version()
        return {
            "remote": remote,
            "local": local,
            "update_available": not self._same_version(local, remote),
        }

    def _local_version(self) -> dict:
        if not self.version_cache.exists():
            return {}
        try:
            return orjson.loads(self.version_cache.read_bytes())
        except Exception:
            return {}

    def _local_index(self) -> dict[str, Any]:
        if not self.index_cache.exists():
            return {}
        try:
            payload = orjson.loads(self.index_cache.read_bytes())
            return payload if isinstance(payload, dict) else {}
        except Exception:
            return {}

    def _diff_records(self, records: list[DatasetRecord]) -> dict[str, Any]:
        previous = self._local_index()
        previous_ids = set(previous.get("ids", []) or [])
        current_ids = {record.id for record in records}
        previous_by_key = previous.get("by_key", {}) or {}
        modified = 0
        for record in records:
            old_id = previous_by_key.get(_record_key(record))
            if old_id and old_id != record.id:
                modified += 1
        return {
            "new_ids": sorted(current_ids - previous_ids),
            "removed_ids": sorted(previous_ids - current_ids),
            "modified_records": modified,
        }

    def _build_index(self, records: list[DatasetRecord], version: dict) -> dict[str, Any]:
        return {
            "version": version.get("version", ""),
            "updated": version.get("updated", ""),
            "records": len(records),
            "ids": sorted(record.id for record in records),
            "by_key": {_record_key(record): record.id for record in records},
        }

    async def _fetch_records(self, client: ApiClient) -> list[DatasetRecord]:
        urls = [
            f"{self.base_url}/data/latest.json",
            f"{self.base_url}/data/latest/latest.json",
        ]
        last_error: Exception | None = None
        for url in urls:
            try:
                payload = await client.get_json(url)
                if not isinstance(payload, list):
                    raise RuntimeError(f"Dataset payload must be a JSON list: {url}")
                return [DatasetRecord(**item) for item in payload]
            except Exception as exc:
                last_error = exc
        raise RuntimeError(f"Could not download GitHub dataset: {last_error}")

    @staticmethod
    def _same_version(local: dict, remote: dict) -> bool:
        local_version = str(local.get("version", ""))
        remote_version = str(remote.get("version", ""))
        local_records = int(local.get("records", local.get("total_items", 0)) or 0)
        remote_records = int(remote.get("records", remote.get("total_items", 0)) or 0)
        return bool(local_version) and local_version == remote_version and local_records == remote_records


def _record_key(record: DatasetRecord) -> str:
    return f"{record.protocol.lower()}:{record.server.lower()}:{record.port}"


def _atomic_write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_bytes(orjson.dumps(payload, option=orjson.OPT_INDENT_2))
    temp.replace(path)
