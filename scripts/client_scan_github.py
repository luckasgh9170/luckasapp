from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.github_sync import GitHubDatasetClient


async def run(base_url: str) -> None:
    result = await GitHubDatasetClient(ROOT, base_url).sync()
    print(result)


def main() -> int:
    parser = argparse.ArgumentParser(description="Scan GitHub distribution dataset and merge into local SQLite.")
    parser.add_argument("base_url")
    args = parser.parse_args()
    asyncio.run(run(args.base_url))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
