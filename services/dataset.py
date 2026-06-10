from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterable

import orjson

from models.dataset import DatasetRecord, DatasetVersion
from models.config import ProxyConfig
from services.config_details import extract_config_info
from services.parser import extract_configs, stable_id


class DatasetStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.base = root / "distribution"
        self.latest_dir = self.base / "data" / "latest"
        self.archive_dir = self.base / "data" / "archive"
        self.metadata_dir = self.base / "metadata"
        self.stats_dir = self.base / "stats"
        for path in (self.latest_dir, self.archive_dir, self.metadata_dir, self.stats_dir):
            path.mkdir(parents=True, exist_ok=True)
        self.latest_path = self.latest_dir / "latest.json"
        self.version_path = self.base / "version.json"
        self.index_path = self.base / "index.json"
        self.stats_path = self.stats_dir / "stats.json"

    def records(self) -> list[DatasetRecord]:
        if not self.latest_path.exists():
            return []
        try:
            return [DatasetRecord(**item) for item in orjson.loads(self.latest_path.read_bytes())]
        except Exception:
            return []

    def merge_text(
        self,
        text: str,
        *,
        source: str,
        source_type: str,
        created_at: str | None = None,
        message_id: int | None = None,
    ) -> tuple[list[DatasetRecord], int]:
        records = []
        for config in extract_configs(text):
            record = canonical_record(
                config.raw,
                source=source,
                source_type=source_type,
                created_at=created_at or _utc_now(),
                message_id=message_id,
                remark=config.name,
            )
            if record:
                records.append(record)
        return self.merge_records(records)

    def merge_records(self, incoming: Iterable[DatasetRecord]) -> tuple[list[DatasetRecord], int]:
        current = {record.id: record for record in self.records()}
        new_count = 0
        for record in incoming:
            if record.id not in current:
                new_count += 1
            current[record.id] = record
        records = sorted(current.values(), key=lambda item: (item.protocol, item.server, item.port, item.id))
        self.write(records, new_count)
        return records, new_count

    def write(self, records: list[DatasetRecord], new_count: int = 0) -> None:
        payload = [record.model_dump(mode="json") for record in records]
        now = _utc_now()
        self.latest_path.write_bytes(orjson.dumps(payload, option=orjson.OPT_INDENT_2))
        archive_path = self.archive_dir / f"{now.replace(':', '-').replace('Z', '')}.json"
        archive_path.write_bytes(orjson.dumps(payload, option=orjson.OPT_INDENT_2))
        version = self._next_version()
        version_doc = DatasetVersion(version=version, updated=now, total_items=len(records), new_items=new_count)
        self.version_path.write_bytes(orjson.dumps(version_doc.model_dump(mode="json"), option=orjson.OPT_INDENT_2))
        protocols = Counter(record.protocol for record in records)
        index_doc = {
            "version": version,
            "updated": now,
            "files": {
                "latest": "data/latest/latest.json",
                "version": "version.json",
                "stats": "stats/stats.json",
            },
            "protocols": dict(sorted(protocols.items())),
            "total_items": len(records),
        }
        self.index_path.write_bytes(orjson.dumps(index_doc, option=orjson.OPT_INDENT_2))
        self.stats_path.write_bytes(orjson.dumps(dataset_stats(records), option=orjson.OPT_INDENT_2))

    def _next_version(self) -> str:
        if not self.version_path.exists():
            return "1.0.1"
        try:
            current = orjson.loads(self.version_path.read_bytes()).get("version", "1.0.0")
            major, minor, patch = [int(part) for part in current.split(".")]
            return f"{major}.{minor}.{patch + 1}"
        except Exception:
            return "1.0.1"


def canonical_record(
    raw: str,
    *,
    source: str,
    source_type: str,
    created_at: str,
    message_id: int | None = None,
    remark: str = "",
) -> DatasetRecord | None:
    details = extract_config_info(raw)
    if details is None or not details.server or not details.port:
        return None
    security = "reality" if details.reality else "tls" if details.tls else "none"
    return DatasetRecord(
        id=stable_id(raw),
        protocol=details.protocol,
        server=details.server,
        port=details.port,
        uuid=details.uuid,
        transport=details.transport_type,
        security=security,
        sni=details.sni,
        remark=remark or details.server,
        tag=f"{details.protocol}:{details.server}:{details.port}",
        source=source,
        source_type=source_type,
        message_id=message_id,
        created_at=created_at,
        raw=raw,
    )


def dataset_record_to_config(record: DatasetRecord) -> ProxyConfig:
    return ProxyConfig(
        id=record.id,
        protocol=record.protocol,
        raw=record.raw,
        name=record.remark or record.server,
        host=record.server,
        port=record.port,
    )


def dataset_stats(records: list[DatasetRecord]) -> dict:
    now = datetime.now(UTC)
    today = now.date().isoformat()
    month = now.strftime("%Y-%m")
    current_year, current_week, _ = now.isocalendar()
    return {
        "total_records": len(records),
        "records_added_today": sum(1 for item in records if item.created_at.startswith(today)),
        "records_added_this_week": sum(1 for item in records if _same_week(item.created_at, current_year, current_week)),
        "records_added_this_month": sum(1 for item in records if item.created_at.startswith(month)),
        "protocols": dict(Counter(item.protocol for item in records)),
        "sources": dict(Counter(item.source for item in records)),
        "updated": _utc_now(),
    }


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _same_week(value: str, year: int, week: int) -> bool:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        iso = parsed.isocalendar()
        return iso.year == year and iso.week == week
    except Exception:
        return False
