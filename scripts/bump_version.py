from __future__ import annotations

import argparse
from datetime import UTC, datetime
from pathlib import Path

import orjson


ROOT = Path(__file__).resolve().parents[1]
VERSION_PATH = ROOT / "version.json"
DEFAULT_DOWNLOAD_URL = "https://github.com/luckasgh9170/luckasapp/releases/latest/download/LuckasApp-windows.zip"


def main() -> int:
    parser = argparse.ArgumentParser(description="Update application version metadata.")
    parser.add_argument("--version", required=True)
    parser.add_argument("--notes", default="")
    parser.add_argument("--download-url", default=DEFAULT_DOWNLOAD_URL)
    args = parser.parse_args()
    current = {}
    if VERSION_PATH.exists():
        current = orjson.loads(VERSION_PATH.read_bytes())
    build = int(current.get("build", 99)) + 1
    payload = {
        "version": args.version,
        "build": build,
        "updated_at": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "release_notes": args.notes,
        "owner": current.get("owner", "luckasgh9170"),
        "repository": current.get("repository", "luckasapp"),
        "download_url": args.download_url,
        "release_url": current.get("release_url", "https://github.com/luckasgh9170/luckasapp/releases/latest"),
        "minimum_supported_build": current.get("minimum_supported_build", 100),
    }
    VERSION_PATH.write_bytes(orjson.dumps(payload, option=orjson.OPT_INDENT_2))
    print(f"{payload['version']} build {payload['build']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
