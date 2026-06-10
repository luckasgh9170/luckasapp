from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import orjson


class HistoryStore:
    def __init__(self, root: Path) -> None:
        self.path = root / "cache" / "connection_history.jsonl"
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def add(self, event: str, payload: dict[str, Any]) -> None:
        record = {
            "time": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            "event": event,
            **payload,
        }
        with self.path.open("ab") as handle:
            handle.write(orjson.dumps(record))
            handle.write(b"\n")

    def list(self, limit: int = 80) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        rows = self.path.read_bytes().splitlines()[-limit:]
        items: list[dict[str, Any]] = []
        for row in rows:
            try:
                items.append(orjson.loads(row))
            except Exception:
                continue
        items.reverse()
        return items
