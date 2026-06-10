from __future__ import annotations

import os
import subprocess
from pathlib import Path


class GitHubDistributionPublisher:
    def __init__(self, root: Path, repo_path: Path | None = None) -> None:
        self.root = root
        self.repo_path = repo_path or Path(os.getenv("GITHUB_DISTRIBUTION_PATH", str(root / "distribution")))

    def publish(self, message: str = "Update dataset") -> str:
        if not (self.repo_path / ".git").exists():
            return "Distribution folder is not a git repository. Initialize or clone it first."
        commands = [
            ["git", "add", "."],
            ["git", "commit", "-m", message],
            ["git", "push"],
        ]
        outputs = []
        for command in commands:
            completed = subprocess.run(command, cwd=str(self.repo_path), capture_output=True, text=True)
            text = (completed.stdout + completed.stderr).strip()
            outputs.append(text)
            if completed.returncode != 0 and "nothing to commit" not in text.lower():
                return text or f"Command failed: {' '.join(command)}"
        return "\n".join(item for item in outputs if item) or "Published."
