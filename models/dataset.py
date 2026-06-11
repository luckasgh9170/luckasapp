from __future__ import annotations

from pydantic import BaseModel


class DatasetRecord(BaseModel):
    id: str
    content_hash: str = ""
    protocol: str
    server: str
    port: int
    country: str = "Unknown"
    isp: str = "Unknown"
    uuid: str = ""
    transport: str = ""
    security: str = ""
    sni: str = ""
    remark: str = ""
    tag: str = ""
    source: str = ""
    source_channel: str = ""
    source_type: str = ""
    message_id: int | None = None
    message_date: str = ""
    created_at: str = ""
    updated_at: str = ""
    ping: int | None = None
    health: int = 0
    stability: int = 0
    score: int = 0
    status: str = "unknown"
    last_check: str = ""
    raw: str


class DatasetVersion(BaseModel):
    version: str = "1.0.0"
    updated: str = ""
    records: int = 0
    total_items: int = 0
    new_records: int = 0
    new_items: int = 0
