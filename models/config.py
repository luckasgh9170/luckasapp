from __future__ import annotations

from enum import StrEnum
from typing import Optional

from pydantic import BaseModel, Field


class ConfigStatus(StrEnum):
    UNKNOWN = "unknown"
    TESTING = "testing"
    HEALTHY = "healthy"
    WORKING = "working"
    UNSTABLE = "unstable"
    SLOW = "slow"
    ONLINE = "online"
    OFFLINE = "offline"
    TIMEOUT = "timeout"
    INVALID = "invalid"
    CONNECTED = "connected"


class ProxyConfig(BaseModel):
    id: str
    protocol: str
    raw: str
    name: str = "Unnamed"
    host: str = ""
    port: int = 0
    country: str = "Unknown"
    isp: str = "Unknown"
    ping_ms: Optional[int] = None
    connection_time_ms: Optional[int] = None
    handshake_time_ms: Optional[int] = None
    response_time_ms: Optional[int] = None
    status: ConfigStatus = ConfigStatus.UNKNOWN
    status_detail: str = ""
    last_check_at: str = ""
    success_count: int = 0
    failure_count: int = 0
    favorite: bool = False
    score: float = Field(default=0.0, ge=0.0)
