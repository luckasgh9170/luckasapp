from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import orjson

from database.db import Database
from models.config import ProxyConfig
from models.dataset import DatasetRecord
from services.dataset import DatasetStore, canonical_record, dataset_record_to_config
from services.health import HealthChecker, is_ready_status


class ServerProcessingPipeline:
    def __init__(self, root: Path, *, timeout: float = 8.0, workers: int = 16) -> None:
        self.root = root
        self.timeout = timeout
        self.workers = max(1, workers)
        self.store = DatasetStore(root)
        self.db = Database(root)

    async def validate_distribution(self, *, limit: int | None = None) -> dict:
        records = self.store.records()
        configs = [dataset_record_to_config(record) for record in records]
        if limit is not None:
            configs = configs[: max(0, limit)]
        checker = HealthChecker(self.root, timeout=self.timeout)
        checked = await checker.check_many(configs, limit=self.workers)
        self.db.upsert_configs(checked)
        return write_processed_servers(self.root, checked, source="backend-validation")

    def publish_from_cache(self, *, limit: int | None = None) -> dict:
        configs = self.db.list_configs()
        if limit is not None:
            configs = configs[: max(0, limit)]
        return write_processed_servers(self.root, configs, source="local-cache")


def write_processed_servers(root: Path, configs: list[ProxyConfig], *, source: str) -> dict:
    data_dir = root / "distribution" / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    now = _utc_now()
    healthy = [config for config in configs if is_ready_status(config.status.value)]
    healthy.sort(key=_server_rank_key)
    records = [_record_from_config(config, source=source, checked_at=now) for config in healthy]
    payload = [record.model_dump(mode="json") for record in records]
    metadata = {
        "updated": now,
        "source": source,
        "input_configs": len(configs),
        "processed_servers": len(records),
        "healthy_servers": len(records),
        "status": "ready",
        "ranking": ["health", "ping", "stability", "last_check"],
        "client_policy": {
            "client_side_bulk_validation": False,
            "client_side_ranking": False,
            "connect_time_light_verification": True,
        },
    }
    _atomic_write_json(data_dir / "servers.json", payload)
    _atomic_write_json(data_dir / "healthy.json", payload)
    _atomic_write_json(data_dir / "server_metadata.json", metadata)
    _update_distribution_version(root, len(records), now)
    return metadata


def _record_from_config(config: ProxyConfig, *, source: str, checked_at: str) -> DatasetRecord:
    record = canonical_record(
        config.raw,
        source=source,
        source_type="processed",
        created_at=config.last_check_at or checked_at,
        remark=config.name,
    )
    if record is None:
        raise ValueError(f"Could not build processed record for {config.id}")
    ping = config.ping_ms if config.ping_ms is not None else config.response_time_ms
    total = config.success_count + config.failure_count
    stability = int((config.success_count / total) * 100) if total else 100
    score = int(round(float(config.score or 0)))
    record.country = config.country
    record.isp = config.isp
    record.ping = ping
    record.health = score
    record.stability = stability
    record.score = score
    record.status = config.status.value
    record.last_check = config.last_check_at or checked_at
    record.updated_at = checked_at
    return record


def _server_rank_key(config: ProxyConfig) -> tuple:
    ping = config.ping_ms if config.ping_ms is not None else config.response_time_ms
    return (-float(config.score or 0), ping if ping is not None else 999999, config.last_check_at or "")


def _update_distribution_version(root: Path, processed_servers: int, processed_at: str) -> None:
    path = root / "distribution" / "version.json"
    if path.exists():
        try:
            payload = orjson.loads(path.read_bytes())
        except Exception:
            payload = {}
    else:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    payload.setdefault("version", "1.0.0")
    payload["processed_at"] = processed_at
    payload["processed_servers"] = processed_servers
    payload["server_list"] = "data/servers.json"
    _atomic_write_json(path, payload)


def _atomic_write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_bytes(orjson.dumps(payload, option=orjson.OPT_INDENT_2))
    temp.replace(path)


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
