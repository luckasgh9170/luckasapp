from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.github_distribution import GitHubDistributionPublisher
from services.telegram_collector import TelegramChannelCollector


async def main_loop(channel: str, interval: int, limit: int, publish: bool) -> None:
    collector = TelegramChannelCollector(ROOT, channel=channel)
    while True:
        try:
            records, new_count = await collector.sync(limit=limit)
            print(f"[sync] channel={channel} total={len(records)} new={new_count}")
            if publish and new_count:
                print(GitHubDistributionPublisher(ROOT).publish(f"Sync {channel}: {new_count} new configs"))
        except Exception as exc:
            print(f"[error] {exc}")
        await asyncio.sleep(interval)


def main() -> int:
    parser = argparse.ArgumentParser(description="Continuously sync authorized Telegram channel into distribution dataset.")
    parser.add_argument("--channel", default="ConfigsHUB2")
    parser.add_argument("--interval", type=int, default=300)
    parser.add_argument("--limit", type=int, default=300)
    parser.add_argument("--publish", action="store_true")
    args = parser.parse_args()
    asyncio.run(main_loop(args.channel, args.interval, args.limit, args.publish))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
