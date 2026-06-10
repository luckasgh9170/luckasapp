from __future__ import annotations

import subprocess
from datetime import UTC, datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CHANGELOG = ROOT / "CHANGELOG.md"


def _git(*args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(ROOT), *args],
        check=False,
        text=True,
        capture_output=True,
    )
    return result.stdout.strip()


def main() -> int:
    latest_tag = _git("describe", "--tags", "--abbrev=0")
    range_spec = f"{latest_tag}..HEAD" if latest_tag else "HEAD"
    log = _git("log", "--pretty=format:- %s", range_spec)
    if not log:
        log = "- Maintenance update"
    stamp = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    title = latest_tag if latest_tag else "Unreleased"
    CHANGELOG.write_text(f"# Changelog\n\n## {title} - {stamp}\n\n{log}\n", encoding="utf-8")
    print(f"Wrote {CHANGELOG}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
