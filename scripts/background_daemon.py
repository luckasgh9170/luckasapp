from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.background_sync import BackgroundServiceRuntime


async def run(once: bool) -> None:
    runtime = BackgroundServiceRuntime(ROOT)
    if once:
        await runtime.run_once()
    else:
        await runtime.run_forever()


def main() -> int:
    parser = argparse.ArgumentParser(description="Run LuckasApp background sync daemon.")
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    try:
        asyncio.run(run(args.once))
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
