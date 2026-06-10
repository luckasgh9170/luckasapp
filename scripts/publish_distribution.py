from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.github_distribution import GitHubDistributionPublisher


def main() -> int:
    parser = argparse.ArgumentParser(description="Commit and push distribution folder to GitHub.")
    parser.add_argument("--message", default="Update dataset")
    args = parser.parse_args()
    print(GitHubDistributionPublisher(ROOT).publish(args.message))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
