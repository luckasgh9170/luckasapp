from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from database.db import Database
from repositories.sources import SourceRepository
from services.discovery import GitHubDiscoveryEngine, save_discovery_output


async def run(limit: int, max_repos: int, save_sources: bool) -> None:
    engine = GitHubDiscoveryEngine(ROOT, max_repos=max_repos)
    repositories = await engine.discover(limit=limit)
    Database(ROOT).upsert_repositories(repositories)
    output_path = save_discovery_output(ROOT, repositories)
    raw_urls = [url for repository in repositories for url in repository.raw_urls]
    if save_sources:
        SourceRepository(ROOT).extend(raw_urls)
    print(f"Discovered repositories: {len(repositories)}")
    print(f"Raw URLs: {len(raw_urls)}")
    print(f"Output: {output_path}")
    for index, repository in enumerate(repositories[:10], 1):
        print(f"{index}. {repository.owner}/{repository.repository_name} score={repository.score} configs={repository.valid_configs}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Discover public V2Ray/Xray config repositories on GitHub.")
    parser.add_argument("--limit", type=int, default=25)
    parser.add_argument("--max-repos", type=int, default=40)
    parser.add_argument("--save-sources", action="store_true")
    args = parser.parse_args()
    asyncio.run(run(args.limit, args.max_repos, args.save_sources))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
