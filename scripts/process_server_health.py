from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.server_processing import ServerProcessingPipeline


async def main_async() -> int:
    parser = argparse.ArgumentParser(description="Backend-only server validation and processed list publisher.")
    parser.add_argument("--workers", type=int, default=16)
    parser.add_argument("--timeout", type=float, default=8.0)
    parser.add_argument("--limit", type=int, default=1000)
    parser.add_argument(
        "--use-existing-cache",
        action="store_true",
        help="Publish processed servers from already validated local SQLite cache without running network validation.",
    )
    args = parser.parse_args()
    pipeline = ServerProcessingPipeline(ROOT, timeout=args.timeout, workers=args.workers)
    if args.use_existing_cache:
        result = pipeline.publish_from_cache(limit=args.limit if args.limit > 0 else None)
    else:
        result = await pipeline.validate_distribution(limit=args.limit if args.limit > 0 else None)
    print(f"Processed servers: {result['processed_servers']}")
    print(f"Updated: {result['updated']}")
    print(f"Output: {ROOT / 'distribution' / 'data' / 'servers.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main_async()))
