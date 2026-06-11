from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import orjson


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class ServiceStateStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.status_path = root / "cache" / "service_status.json"
        self.log_path = root / "logs" / "service.log"
        self.status_path.parent.mkdir(parents=True, exist_ok=True)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def read(self) -> dict[str, Any]:
        if not self.status_path.exists():
            return {
                "status": "Stopped",
                "updated_at": "",
                "last_sync": "",
                "last_health_check": "",
                "last_processed_update": "",
                "records": 0,
                "healthy": 0,
                "last_error": "",
            }
        try:
            return orjson.loads(self.status_path.read_bytes())
        except Exception:
            return {"status": "Error", "last_error": "Could not read service status."}

    def write(self, **updates: Any) -> dict[str, Any]:
        data = self.read()
        data.update(updates)
        data["updated_at"] = utc_now()
        self.status_path.write_bytes(orjson.dumps(data, option=orjson.OPT_INDENT_2))
        return data

    def log(self, event: str, message: str, **fields: Any) -> None:
        record = {
            "time": utc_now(),
            "event": event,
            "message": message,
            **fields,
        }
        with self.log_path.open("ab") as handle:
            handle.write(orjson.dumps(record))
            handle.write(b"\n")

    def tail(self, lines: int = 120) -> list[str]:
        if not self.log_path.exists():
            return []
        rows = self.log_path.read_bytes().splitlines()[-lines:]
        result: list[str] = []
        for row in rows:
            try:
                item = orjson.loads(row)
                result.append(f"{item.get('time', '')} {item.get('event', '')}: {item.get('message', '')}")
            except Exception:
                result.append(row.decode("utf-8", "ignore"))
        return result
