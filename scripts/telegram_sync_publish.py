from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.github_distribution import GitHubDistributionPublisher
from services.telegram_collector import TelegramChannelCollector


async def run(channel: str, limit: int, publish: bool) -> None:
    collector = TelegramChannelCollector(ROOT, channel=channel)
    records, new_count = await collector.sync(limit=limit)
    print(f"Synced channel: {channel}")
    print(f"Total dataset records: {len(records)}")
    print(f"New records: {new_count}")
    if publish and new_count:
        result = GitHubDistributionPublisher(ROOT).publish(f"Sync {channel}: {new_count} new configs")
        print(result)


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync authorized Telegram channel and optionally publish dataset to GitHub.")
    parser.add_argument("--channel", default="ConfigsHUB2")
    parser.add_argument("--limit", type=int, default=300)
    parser.add_argument("--publish", action="store_true")
    args = parser.parse_args()
    asyncio.run(run(args.channel, args.limit, args.publish))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
