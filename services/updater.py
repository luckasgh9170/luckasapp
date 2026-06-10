from __future__ import annotations

import shutil
import zipfile
from pathlib import Path
from typing import Any

import httpx
import orjson


class UpdateManager:
    def __init__(self, root: Path, version_url: str) -> None:
        self.root = root
        self.version_url = version_url
        self.local_version_path = root / "version.json"
        self.update_dir = root / "cache" / "updates"
        self.update_dir.mkdir(parents=True, exist_ok=True)
        self.pending_path = self.update_dir / "pending_update.json"

    def local_version(self) -> dict[str, Any]:
        if not self.local_version_path.exists():
            return {"version": "0.0.0", "build": 0}
        try:
            return orjson.loads(self.local_version_path.read_bytes())
        except Exception:
            return {"version": "0.0.0", "build": 0}

    async def check(self) -> dict[str, Any]:
        if not self.version_url:
            return {"status": "disabled", "update_available": False}
        local = self.local_version()
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            response = await client.get(self.version_url)
            response.raise_for_status()
            remote = response.json()
        local_build = int(local.get("build", 0) or 0)
        remote_build = int(remote.get("build", 0) or 0)
        skipped = self._skipped_build()
        update_available = remote_build > local_build and remote_build != skipped
        return {
            "status": "checked",
            "update_available": update_available,
            "local": local,
            "remote": remote,
            "local_build": local_build,
            "remote_build": remote_build,
            "skipped_build": skipped,
        }

    async def download_and_stage(self, remote: dict[str, Any]) -> dict[str, Any]:
        download_url = str(remote.get("download_url", "")).strip()
        if not download_url:
            return {"status": "no_asset", "message": "No download_url in version.json."}
        target = self.update_dir / Path(download_url.split("?", 1)[0]).name
        async with httpx.AsyncClient(timeout=120, follow_redirects=True) as client:
            response = await client.get(download_url)
            response.raise_for_status()
            target.write_bytes(response.content)
        staged_dir = self.update_dir / "staged"
        if staged_dir.exists():
            shutil.rmtree(staged_dir)
        staged_dir.mkdir(parents=True, exist_ok=True)
        if target.suffix.lower() == ".zip":
            with zipfile.ZipFile(target) as archive:
                archive.extractall(staged_dir)
        pending = {
            "status": "staged",
            "asset": str(target),
            "staged_dir": str(staged_dir),
            "remote": remote,
        }
        self.pending_path.write_bytes(orjson.dumps(pending, option=orjson.OPT_INDENT_2))
        return pending

    def skip(self, build: int) -> None:
        (self.update_dir / "skip_version.json").write_bytes(orjson.dumps({"build": build}, option=orjson.OPT_INDENT_2))

    def _skipped_build(self) -> int:
        path = self.update_dir / "skip_version.json"
        if not path.exists():
            return -1
        try:
            return int(orjson.loads(path.read_bytes()).get("build", -1))
        except Exception:
            return -1
