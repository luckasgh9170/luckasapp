from __future__ import annotations

import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path


class GitHubDistributionPublisher:
    def __init__(self, root: Path, repo_path: Path | None = None) -> None:
        self.root = root
        env_path = os.getenv("GITHUB_DISTRIBUTION_PATH")
        if repo_path is not None:
            self.repo_path = repo_path
        elif env_path:
            self.repo_path = Path(env_path)
        elif (root / ".git").exists():
            self.repo_path = root
        else:
            self.repo_path = root / "distribution"

    def publish(self, message: str = "Update dataset") -> str:
        if not (self.repo_path / ".git").exists():
            return f"{self.repo_path} is not a git repository. Initialize or clone it first."
        self._ensure_identity()
        add_target = "distribution" if self.repo_path.resolve() == self.root.resolve() else "."
        commands = [["git", "add", add_target]]
        if message == "Update dataset":
            message = self.auto_message(0)
        commands.extend([["git", "commit", "-m", message], ["git", "push"]])
        outputs = []
        for command in commands:
            completed = subprocess.run(command, cwd=str(self.repo_path), capture_output=True, text=True)
            text = (completed.stdout + completed.stderr).strip()
            outputs.append(text)
            if completed.returncode != 0 and "nothing to commit" not in text.lower():
                return text or f"Command failed: {' '.join(command)}"
        return "\n".join(item for item in outputs if item) or "Published."

    @staticmethod
    def auto_message(record_count: int) -> str:
        stamp = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        return f"Auto Sync Update {stamp} Record Count {record_count}"

    def _ensure_identity(self) -> None:
        name = subprocess.run(["git", "config", "user.name"], cwd=str(self.repo_path), capture_output=True, text=True)
        email = subprocess.run(["git", "config", "user.email"], cwd=str(self.repo_path), capture_output=True, text=True)
        if name.returncode != 0 or not name.stdout.strip():
            subprocess.run(["git", "config", "user.name", "LuckasApp Sync"], cwd=str(self.repo_path), check=False)
        if email.returncode != 0 or not email.stdout.strip():
            subprocess.run(["git", "config", "user.email", "sync@luckasapp.local"], cwd=str(self.repo_path), check=False)
