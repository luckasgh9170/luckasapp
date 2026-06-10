from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from database.db import Database
from repositories.sources import SourceRepository
from services.collector import ConfigCollector


async def run(limit_sources: int | None) -> None:
    sources = SourceRepository(ROOT).list()
    if limit_sources:
        sources = sources[:limit_sources]
    collector = ConfigCollector(timeout=18)
    configs = await collector.collect(sources)
    added = Database(ROOT).upsert_configs(configs)
    print(f"Sources: {len(sources)}")
    print(f"Collected configs: {len(configs)}")
    print(f"New configs: {added}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect configs from saved raw/subscription sources.")
    parser.add_argument("--limit-sources", type=int, default=None)
    args = parser.parse_args()
    asyncio.run(run(args.limit_sources))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
