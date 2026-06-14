from __future__ import annotations

import asyncio
import os
import subprocess
from pathlib import Path
from typing import Optional, TextIO

try:
    import psutil
except Exception:  # pragma: no cover
    psutil = None


class CoreManager:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.process: Optional[subprocess.Popen[str]] = None
        self.active_config: Optional[Path] = None
        self._log_handle: TextIO | None = None
        self._lock = asyncio.Lock()
        self.log_path = root / "logs" / "core.log"
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def discover_core(self) -> Optional[Path]:
        for name in ("xray.exe", "v2ray.exe", "xray", "v2ray"):
            candidate = self.root / "core" / "bin" / name
            if candidate.exists() and self._is_valid_core(candidate):
                return candidate
        return None

    def _is_valid_core(self, candidate: Path) -> bool:
        try:
            completed = subprocess.run(
                [str(candidate), "version"],
                cwd=str(self.root),
                capture_output=True,
                text=True,
                timeout=5,
                creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
            )
        except Exception:
            return False
        return completed.returncode == 0 and bool((completed.stdout + completed.stderr).strip())

    async def start(self, config_path: Path) -> str:
        async with self._lock:
            core_path = self.discover_core()
            if core_path is None:
                return "Core binary not found in core/bin"
            await self._stop_locked()
            self.active_config = config_path
            self._log_handle = self.log_path.open("a", encoding="utf-8", errors="ignore")
            self.process = subprocess.Popen(
                [str(core_path), "run", "-config", str(config_path)],
                cwd=str(self.root),
                stdout=self._log_handle,
                stderr=subprocess.STDOUT,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
            )
            return "Core started"

    async def stop(self) -> str:
        async with self._lock:
            await self._stop_locked()
            return "Core stopped"

    async def restart(self) -> str:
        async with self._lock:
            if self.active_config is None:
                return "No active config"
            config_path = self.active_config
            await self._stop_locked()
            core_path = self.discover_core()
            if core_path is None:
                return "Core binary not found in core/bin"
            self._log_handle = self.log_path.open("a", encoding="utf-8", errors="ignore")
            self.process = subprocess.Popen(
                [str(core_path), "run", "-config", str(config_path)],
                cwd=str(self.root),
                stdout=self._log_handle,
                stderr=subprocess.STDOUT,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
            )
            return "Core started"

    def version(self) -> str:
        core_path = self.discover_core()
        if core_path is None:
            return "Not installed"
        try:
            completed = subprocess.run(
                [str(core_path), "version"],
                cwd=str(self.root),
                capture_output=True,
                text=True,
                timeout=5,
                creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
            )
            first_line = (completed.stdout or completed.stderr).splitlines()[0]
            return first_line.strip()
        except Exception:
            return "Unknown"

    def status(self) -> dict:
        running = self.process is not None and self.process.poll() is None
        cpu = 0.0
        memory = 0
        pid = 0
        if running and psutil is not None and self.process is not None:
            try:
                proc = psutil.Process(self.process.pid)
                pid = proc.pid
                cpu = proc.cpu_percent(interval=0.0)
                memory = proc.memory_info().rss
            except Exception:
                pass
        return {
            "running": running,
            "pid": pid,
            "version": self.version(),
            "cpuPercent": round(cpu, 1),
            "memoryBytes": memory,
            "memoryText": _format_bytes(memory),
            "logPath": str(self.log_path),
        }

    def tail_logs(self, lines: int = 120) -> list[str]:
        if not self.log_path.exists():
            return []
        try:
            return self.log_path.read_text(encoding="utf-8", errors="ignore").splitlines()[-lines:]
        except Exception:
            return []

    async def _stop_locked(self) -> None:
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:
                await asyncio.to_thread(self.process.wait, 5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                try:
                    await asyncio.to_thread(self.process.wait, 2)
                except Exception:
                    pass
        self.process = None
        if self._log_handle is not None:
            try:
                self._log_handle.close()
            except Exception:
                pass
            self._log_handle = None


def _format_bytes(value: int | float) -> str:
    value = float(max(0, value))
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024
