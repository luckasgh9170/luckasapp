from __future__ import annotations

import asyncio
import math
import os
import re
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import quote

import httpx
import orjson

from models.repository import RepositoryDiscoveryResult
from services.config_details import extract_config_info
from services.parser import CONFIG_RE, extract_configs


TARGET_FILENAMES = {
    "sub.txt",
    "sub1.txt",
    "sub2.txt",
    "subscription.txt",
    "nodes.txt",
    "configs.txt",
    "all.txt",
    "v2ray.txt",
    "xray.txt",
    "clash.yaml",
    "clash.yml",
    "mihomo.yaml",
    "sing-box.json",
}
TARGET_EXTENSIONS = {".txt", ".json", ".yaml", ".yml"}
TARGET_HINTS = (
    "v2ray",
    "xray",
    "vmess",
    "vless",
    "trojan",
    "hysteria",
    "tuic",
    "clash",
    "mihomo",
    "sing-box",
    "subscription",
    "sub",
    "nodes",
    "configs",
    "proxy",
)
SEARCH_QUERIES = (
    "v2ray configs",
    "xray configs",
    "free v2ray",
    "free xray",
    "free nodes",
    "subscription links",
    "clash subscription",
    "v2ray subscription",
    "xray subscription",
    "vless nodes",
    "vmess nodes",
    "trojan nodes",
    "hysteria configs",
    "tuic configs",
    "free proxy configs",
    "proxy subscription",
    "v2ray-configs",
    "free-v2ray",
    "free-xray",
    "free-node",
    "proxy-pool",
    "node-pool",
    "clash-meta",
    "mihomo",
    "sing-box",
    "subscription-generator",
)


@dataclass(frozen=True)
class CandidateFile:
    path: str
    size: int
    raw_url: str
    original_url: str
    priority: int


@dataclass(frozen=True)
class SeedRepository:
    owner: str
    name: str
    branch: str
    paths: tuple[str, ...]
    description: str = ""

    @property
    def full_name(self) -> str:
        return f"{self.owner}/{self.name}"

    @property
    def repository_url(self) -> str:
        return f"https://github.com/{self.full_name}"


SEED_REPOSITORIES = (
    SeedRepository(
        "MatinGhanbari",
        "v2ray-configs",
        "main",
        tuple(f"subscriptions/v2ray/subs/sub{index}.txt" for index in range(1, 13)),
        "Frequently updated V2Ray subscription split files.",
    ),
    SeedRepository(
        "MohammadBahemmat",
        "V2ray-Collector",
        "main",
        (
            "all_servers.txt",
            "servers/vless_servers.txt",
            "servers/vmess_servers.txt",
            "servers/trojan_servers.txt",
            "servers/ss_servers.txt",
            "servers/ssr_servers.txt",
            "servers/hysteria_servers.txt",
            "servers/hysteria2_servers.txt",
            "servers/tuic_servers.txt",
        ),
        "Automated collector for V2Ray configs from GitHub and Telegram.",
    ),
    SeedRepository(
        "DukeMehdi",
        "FreeList-V2ray-Configs",
        "main",
        (
            "Configs/Lite-DukeMehdi-Configs.txt",
            "Configs/SS-DukeMehdi-Configs.txt",
            "Configs/SSR-DukeMehdi-Configs.txt",
            "Configs/VMESS-DukeMehdi-Configs.txt",
        ),
        "Automated V2Ray free config collection.",
    ),
    SeedRepository(
        "iboxz",
        "free-v2ray-collector",
        "main",
        ("main/mix.txt", "main/vmess.txt", "main/trojan.txt", "main/shadowsocks.txt"),
        "V2Ray config collector with VLESS, VMess, Shadowsocks and Trojan.",
    ),
    SeedRepository(
        "mohammmdmdmkdmewof",
        "v2rayConfigsForYou",
        "main",
        ("configs.txt",),
        "Free V2Ray configs list.",
    ),
    SeedRepository(
        "ALIILAPRO",
        "v2rayNG-Config",
        "main",
        ("sub.txt", "server.txt", "vless.txt", "vmess.txt", "trojan.txt"),
        "v2rayNG config subscriptions.",
    ),
)


class GitHubDiscoveryEngine:
    def __init__(
        self,
        root: Path,
        token: str | None = None,
        max_repos: int = 40,
        max_files_per_repo: int = 12,
        timeout: float = 18.0,
    ) -> None:
        self.root = root
        self.max_repos = max_repos
        self.max_files_per_repo = max_files_per_repo
        self.cutoff = datetime.now(UTC) - timedelta(days=365)
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "LuckasApp-DiscoveryEngine",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        token = token or os.getenv("GITHUB_TOKEN")
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self.client = httpx.AsyncClient(headers=headers, timeout=timeout, follow_redirects=True)

    async def close(self) -> None:
        await self.client.aclose()

    async def discover(self, limit: int = 25) -> list[RepositoryDiscoveryResult]:
        try:
            seed_results = await self._discover_seed_repositories()
            repositories = await self._search_repositories()
            semaphore = asyncio.Semaphore(6)

            async def guarded(item: dict) -> RepositoryDiscoveryResult | None:
                async with semaphore:
                    return await self._analyze_repository(item)

            analyzed = await asyncio.gather(*(guarded(item) for item in repositories[: self.max_repos]))
            merged: dict[str, RepositoryDiscoveryResult] = {
                item.repository_url: item
                for item in seed_results
                if item.valid_configs > 0 and item.raw_urls
            }
            for item in analyzed:
                if item and item.valid_configs > 0 and item.raw_urls:
                    current = merged.get(item.repository_url)
                    if current is None or item.score >= current.score:
                        merged[item.repository_url] = item
            results = list(merged.values())
            results.sort(key=lambda item: (item.score, item.valid_configs, item.stars), reverse=True)
            return results[:limit]
        finally:
            await self.close()

    async def _discover_seed_repositories(self) -> list[RepositoryDiscoveryResult]:
        semaphore = asyncio.Semaphore(6)

        async def guarded(seed: SeedRepository) -> RepositoryDiscoveryResult | None:
            async with semaphore:
                return await self._analyze_seed_repository(seed)

        results = await asyncio.gather(*(guarded(seed) for seed in SEED_REPOSITORIES))
        return [result for result in results if result]

    async def _analyze_seed_repository(self, seed: SeedRepository) -> RepositoryDiscoveryResult | None:
        candidates = [
            CandidateFile(
                path=path,
                size=0,
                raw_url=_github_raw_url(seed.full_name, seed.branch, path),
                original_url=_github_blob_url(seed.full_name, seed.branch, path),
                priority=10,
            )
            for path in seed.paths
        ]
        fetched = await asyncio.gather(*(self._fetch_candidate(candidate) for candidate in candidates))
        fetched = [item for item in fetched if item]
        if not fetched:
            return None

        valid_configs = 0
        config_count = 0
        protocols: Counter[str] = Counter()
        raw_urls: list[str] = []
        original_urls: list[str] = []

        for candidate, text in fetched:
            raw_hits = CONFIG_RE.findall(text)
            config_count += len(raw_hits)
            parsed_configs = extract_configs(text)
            if not parsed_configs:
                continue
            raw_urls.append(candidate.raw_url)
            original_urls.append(candidate.original_url)
            valid_configs += len(parsed_configs)
            for config in parsed_configs:
                details = extract_config_info(config.raw)
                protocols[details.protocol if details else config.protocol] += 1

        if valid_configs == 0:
            return None

        score = _score_repository(
            last_update=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            stars=0,
            forks=0,
            valid_configs=valid_configs,
            config_count=max(config_count, valid_configs),
            fetched_count=len(fetched),
            candidate_count=len(candidates),
            subscription_files_count=len(raw_urls),
        )
        return RepositoryDiscoveryResult(
            repository_name=seed.name,
            owner=seed.owner,
            last_update=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            description=seed.description,
            repository_url=seed.repository_url,
            original_urls=original_urls,
            raw_urls=raw_urls,
            subscription_files_count=len(raw_urls),
            protocols=sorted(protocols),
            config_count=max(config_count, valid_configs),
            valid_configs=valid_configs,
            score=score,
        )

    async def _search_repositories(self) -> list[dict]:
        collected: dict[str, dict] = {}
        cutoff_text = self.cutoff.date().isoformat()
        for query in SEARCH_QUERIES:
            if len(collected) >= self.max_repos:
                break
            params = {
                "q": f"{query} pushed:>={cutoff_text} archived:false",
                "sort": "updated",
                "order": "desc",
                "per_page": "10",
            }
            try:
                response = await self.client.get("https://api.github.com/search/repositories", params=params)
                if response.status_code in {403, 429}:
                    break
                response.raise_for_status()
            except httpx.HTTPError:
                continue
            for item in response.json().get("items", []):
                if item.get("archived"):
                    continue
                full_name = item.get("full_name", "")
                pushed_at = _parse_datetime(item.get("pushed_at", ""))
                if full_name and pushed_at and pushed_at >= self.cutoff:
                    collected.setdefault(full_name, item)
        return list(collected.values())

    async def _analyze_repository(self, item: dict) -> RepositoryDiscoveryResult | None:
        full_name = item.get("full_name", "")
        if "/" not in full_name:
            return None
        owner, repository_name = full_name.split("/", 1)
        branch = item.get("default_branch") or "main"
        tree = await self._repository_tree(full_name, branch)
        if not tree:
            return None

        candidates = self._candidate_files(full_name, branch, tree)
        if not candidates:
            return None

        candidates = candidates[: self.max_files_per_repo]
        fetched = await asyncio.gather(*(self._fetch_candidate(candidate) for candidate in candidates))
        fetched = [item for item in fetched if item]
        if not fetched:
            return None

        valid_configs = 0
        config_count = 0
        protocols: Counter[str] = Counter()
        raw_urls: list[str] = []
        original_urls: list[str] = []

        for candidate, text in fetched:
            raw_hits = CONFIG_RE.findall(text)
            config_count += len(raw_hits)
            parsed_configs = extract_configs(text)
            if not parsed_configs:
                continue
            raw_urls.append(candidate.raw_url)
            original_urls.append(candidate.original_url)
            valid_configs += len(parsed_configs)
            for config in parsed_configs:
                details = extract_config_info(config.raw)
                protocols[details.protocol if details else config.protocol] += 1

        if valid_configs == 0:
            return None

        last_update = item.get("pushed_at", "")
        score = _score_repository(
            last_update=last_update,
            stars=int(item.get("stargazers_count", 0) or 0),
            forks=int(item.get("forks_count", 0) or 0),
            valid_configs=valid_configs,
            config_count=max(config_count, valid_configs),
            fetched_count=len(fetched),
            candidate_count=len(candidates),
            subscription_files_count=len(raw_urls),
        )
        return RepositoryDiscoveryResult(
            repository_name=repository_name,
            owner=owner,
            stars=int(item.get("stargazers_count", 0) or 0),
            forks=int(item.get("forks_count", 0) or 0),
            last_update=last_update,
            language=item.get("language") or "",
            description=item.get("description") or "",
            repository_url=item.get("html_url") or f"https://github.com/{full_name}",
            original_urls=original_urls,
            raw_urls=raw_urls,
            subscription_files_count=len(raw_urls),
            protocols=sorted(protocols),
            config_count=max(config_count, valid_configs),
            valid_configs=valid_configs,
            score=score,
        )

    async def _repository_tree(self, full_name: str, branch: str) -> list[dict]:
        url = f"https://api.github.com/repos/{full_name}/git/trees/{quote(branch, safe='')}?recursive=1"
        try:
            response = await self.client.get(url)
            if response.status_code == 404 and branch != "master":
                response = await self.client.get(f"https://api.github.com/repos/{full_name}/git/trees/master?recursive=1")
            if response.status_code in {403, 429}:
                return []
            response.raise_for_status()
        except httpx.HTTPError:
            return []
        data = response.json()
        if data.get("truncated"):
            return []
        return data.get("tree", [])

    def _candidate_files(self, full_name: str, branch: str, tree: list[dict]) -> list[CandidateFile]:
        candidates: list[CandidateFile] = []
        for node in tree:
            if node.get("type") != "blob":
                continue
            path = node.get("path", "")
            size = int(node.get("size", 0) or 0)
            if not path or size <= 0 or size > 2_500_000:
                continue
            priority = _file_priority(path)
            if priority <= 0:
                continue
            encoded_path = quote(path, safe="/")
            raw_url = _github_raw_url(full_name, branch, path)
            original_url = _github_blob_url(full_name, branch, path)
            candidates.append(CandidateFile(path, size, raw_url, original_url, priority))
        candidates.sort(key=lambda item: (item.priority, -item.size), reverse=True)
        return candidates

    async def _fetch_candidate(self, candidate: CandidateFile) -> tuple[CandidateFile, str] | None:
        try:
            response = await self.client.get(candidate.raw_url)
            if response.status_code >= 400:
                return None
            text = response.text
        except httpx.HTTPError:
            return None
        if not _looks_like_subscription(text):
            return None
        return candidate, text


def save_discovery_output(root: Path, repositories: list[RepositoryDiscoveryResult]) -> Path:
    path = root / "cache" / "discovered_repositories.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = [repository.model_dump(mode="json") for repository in repositories]
    path.write_bytes(orjson.dumps(payload, option=orjson.OPT_INDENT_2))
    return path


def _github_raw_url(full_name: str, branch: str, path: str) -> str:
    return f"https://raw.githubusercontent.com/{full_name}/{quote(branch, safe='')}/{quote(path, safe='/')}"


def _github_blob_url(full_name: str, branch: str, path: str) -> str:
    return f"https://github.com/{full_name}/blob/{quote(branch, safe='')}/{quote(path, safe='/')}"


def _file_priority(path: str) -> int:
    lower = path.lower()
    name = lower.rsplit("/", 1)[-1]
    extension = "." + name.rsplit(".", 1)[-1] if "." in name else ""
    if extension not in TARGET_EXTENSIONS:
        return 0
    score = 0
    if name in TARGET_FILENAMES:
        score += 8
    if any(hint in lower for hint in TARGET_HINTS):
        score += 5
    if re.search(r"(^|/)(sub|subscribe|subscription|node|nodes|config|configs|clash|v2ray|xray)(\d+)?\.", lower):
        score += 4
    if "/test" in lower or "/example" in lower or "/docs" in lower:
        score -= 4
    return max(score, 0)


def _looks_like_subscription(text: str) -> bool:
    if CONFIG_RE.search(text):
        return True
    compact = text.strip()
    if len(compact) < 24:
        return False
    try:
        import base64

        padded = compact + "=" * (-len(compact) % 4)
        decoded = base64.urlsafe_b64decode(padded).decode("utf-8", "ignore")
        return CONFIG_RE.search(decoded) is not None
    except Exception:
        return False


def _score_repository(
    *,
    last_update: str,
    stars: int,
    forks: int,
    valid_configs: int,
    config_count: int,
    fetched_count: int,
    candidate_count: int,
    subscription_files_count: int,
) -> int:
    pushed = _parse_datetime(last_update)
    days = (datetime.now(UTC) - pushed).days if pushed else 365
    freshness = max(0.0, 35.0 * (1.0 - min(days, 365) / 365))
    quantity = min(valid_configs, 500) / 500 * 25
    ratio = valid_configs / max(config_count, 1) * 15
    availability = fetched_count / max(candidate_count, 1) * 10
    community = min(10.0, math.log10(stars + 1) * 6 + math.log10(forks + 1) * 3)
    file_bonus = min(5.0, subscription_files_count)
    return int(round(min(100.0, freshness + quantity + ratio + availability + community + file_bonus)))


def _parse_datetime(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
