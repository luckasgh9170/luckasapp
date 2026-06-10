from __future__ import annotations

from pydantic import BaseModel, Field


class ExtractedConfigInfo(BaseModel):
    protocol: str
    server: str = ""
    port: int = 0
    uuid: str = ""
    transport_type: str = ""
    tls: bool = False
    reality: bool = False
    sni: str = ""
    country: str = "Unknown"


class RepositoryDiscoveryResult(BaseModel):
    repository_name: str
    owner: str
    stars: int = 0
    forks: int = 0
    last_update: str = ""
    language: str = ""
    description: str = ""
    repository_url: str = ""
    original_urls: list[str] = Field(default_factory=list)
    raw_urls: list[str] = Field(default_factory=list)
    subscription_files_count: int = 0
    protocols: list[str] = Field(default_factory=list)
    config_count: int = 0
    valid_configs: int = 0
    score: int = 0
