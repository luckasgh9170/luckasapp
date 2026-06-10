from __future__ import annotations

from pathlib import Path

import orjson


class SourceRepository:
    def __init__(self, root: Path) -> None:
        self.path = root / "cache" / "sources.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def list(self) -> list[str]:
        if not self.path.exists():
            return []
        try:
            return list(orjson.loads(self.path.read_bytes()))
        except Exception:
            return []

    def add(self, url: str) -> list[str]:
        url = url.strip()
        sources = self.list()
        if url and url not in sources:
            sources.append(url)
            self.path.write_bytes(orjson.dumps(sources, option=orjson.OPT_INDENT_2))
        return sources

    def extend(self, urls: list[str]) -> list[str]:
        sources = self.list()
        seen = set(sources)
        for url in urls:
            url = url.strip()
            if url and url not in seen:
                seen.add(url)
                sources.append(url)
        self.path.write_bytes(orjson.dumps(sources, option=orjson.OPT_INDENT_2))
        return sources

    def remove(self, url: str) -> list[str]:
        sources = [source for source in self.list() if source != url]
        self.path.write_bytes(orjson.dumps(sources, option=orjson.OPT_INDENT_2))
        return sources
