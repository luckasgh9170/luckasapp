from __future__ import annotations

from pydantic import BaseModel


class DatasetRecord(BaseModel):
    id: str
    protocol: str
    server: str
    port: int
    uuid: str = ""
    transport: str = ""
    security: str = ""
    sni: str = ""
    remark: str = ""
    tag: str = ""
    source: str = ""
    source_type: str = ""
    message_id: int | None = None
    created_at: str = ""
    raw: str


class DatasetVersion(BaseModel):
    version: str = "1.0.0"
    updated: str = ""
    total_items: int = 0
    new_items: int = 0
