from __future__ import annotations

import os
from datetime import UTC
from pathlib import Path

import orjson

from models.dataset import DatasetRecord
from services.dataset import DatasetStore, canonical_record
from services.parser import extract_configs


class TelegramChannelCollector:
    def __init__(self, root: Path, channel: str = "ConfigsHUB2") -> None:
        self.root = root
        self.channel = channel
        self.state_path = root / "cache" / "telegram_state.json"
        self.messages_path = root / "cache" / "telegram_messages.jsonl"
        self.session_path = root / "cache" / "telegram_collector"
        self.state_path.parent.mkdir(parents=True, exist_ok=True)

    async def sync(self, limit: int = 300) -> tuple[list[DatasetRecord], int]:
        try:
            from telethon import TelegramClient
        except ImportError as exc:
            raise RuntimeError("Telethon is not installed. Run pip install -r requirements.txt") from exc

        api_id = os.getenv("TELEGRAM_API_ID")
        api_hash = os.getenv("TELEGRAM_API_HASH")
        if not api_id or not api_hash:
            raise RuntimeError("Set TELEGRAM_API_ID and TELEGRAM_API_HASH before syncing Telegram.")

        last_id = self._last_message_id()
        records: list[DatasetRecord] = []
        max_seen = last_id
        async with TelegramClient(str(self.session_path), int(api_id), api_hash) as client:
            async for message in client.iter_messages(self.channel, min_id=last_id, limit=limit, reverse=True):
                text = message.message or ""
                created_at = message.date.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
                parsed = []
                for config in extract_configs(text):
                    record = canonical_record(
                        config.raw,
                        source=self.channel,
                        source_type="telegram",
                        created_at=created_at,
                        message_id=message.id,
                        remark=config.name,
                    )
                    if record:
                        records.append(record)
                        parsed.append(record.model_dump(mode="json"))
                self._append_message(
                    {
                        "message_id": message.id,
                        "publish_date": created_at,
                        "original_content": text,
                        "parsed_content": parsed,
                        "source_metadata": {"channel": self.channel},
                    }
                )
                max_seen = max(max_seen, int(message.id))
        if max_seen > last_id:
            self._write_state(max_seen)
        merged, new_count = DatasetStore(self.root).merge_records(records)
        return merged, new_count

    def _last_message_id(self) -> int:
        if not self.state_path.exists():
            return 0
        try:
            return int(orjson.loads(self.state_path.read_bytes()).get("last_message_id", 0))
        except Exception:
            return 0

    def _write_state(self, last_message_id: int) -> None:
        self.state_path.write_bytes(orjson.dumps({"channel": self.channel, "last_message_id": last_message_id}, option=orjson.OPT_INDENT_2))

    def _append_message(self, payload: dict) -> None:
        with self.messages_path.open("ab") as handle:
            handle.write(orjson.dumps(payload))
            handle.write(b"\n")
