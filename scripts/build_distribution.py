from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from database.db import Database
from services.dataset import DatasetStore, canonical_record


def main() -> int:
    parser = argparse.ArgumentParser(description="Build GitHub distribution dataset from local SQLite configs.")
    parser.add_argument("--source", default="local-cache")
    args = parser.parse_args()
    records = []
    for config in Database(ROOT).list_configs():
        record = canonical_record(
            config.raw,
            source=args.source,
            source_type="local",
            created_at=config.last_check_at or "",
            remark=config.name,
        )
        if record:
            records.append(record)
    merged, new_count = DatasetStore(ROOT).merge_records(records)
    print(f"Distribution records: {len(merged)}")
    print(f"New records: {new_count}")
    print(f"Output: {ROOT / 'distribution'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
