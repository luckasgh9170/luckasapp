from __future__ import annotations

import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import orjson

try:
    import psutil
except Exception:  # pragma: no cover
    psutil = None


def format_bytes(value: int | float) -> str:
    value = float(max(0, value))
    units = ("B", "KB", "MB", "GB", "TB")
    for unit in units:
        if value < 1024 or unit == units[-1]:
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024
    return f"{value:.1f} TB"


class TrafficMonitor:
    def __init__(self, root: Path) -> None:
        self.path = root / "cache" / "traffic_usage.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.storage = self._load()
        self.active = False
        self.started_at = 0.0
        self.last_time = time.monotonic()
        self.last_sent = 0
        self.last_recv = 0
        self.session_upload = 0
        self.session_download = 0
        self.peak_upload_speed = 0
        self.peak_download_speed = 0
        self.upload_speed = 0
        self.download_speed = 0
        self.speed_points: list[dict[str, int]] = []
        self._prime()

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"daily": {}, "weekly": {}, "monthly": {}, "lifetime_upload": 0, "lifetime_download": 0}
        try:
            data = orjson.loads(self.path.read_bytes())
            data.setdefault("daily", {})
            data.setdefault("weekly", {})
            data.setdefault("monthly", {})
            data.setdefault("lifetime_upload", 0)
            data.setdefault("lifetime_download", 0)
            return data
        except Exception:
            return {"daily": {}, "weekly": {}, "monthly": {}, "lifetime_upload": 0, "lifetime_download": 0}

    def _save(self) -> None:
        self.path.write_bytes(orjson.dumps(self.storage, option=orjson.OPT_INDENT_2))

    def _counters(self) -> tuple[int, int]:
        if psutil is None:
            return self.last_sent, self.last_recv
        counters = psutil.net_io_counters()
        return int(counters.bytes_sent), int(counters.bytes_recv)

    def _prime(self) -> None:
        self.last_sent, self.last_recv = self._counters()
        self.last_time = time.monotonic()

    def start_session(self) -> None:
        self.active = True
        self.started_at = time.monotonic()
        self.session_upload = 0
        self.session_download = 0
        self.peak_upload_speed = 0
        self.peak_download_speed = 0
        self.speed_points.clear()
        self._prime()

    def stop_session(self) -> None:
        self.sample()
        self.active = False
        self._save()

    def sample(self) -> dict[str, Any]:
        now = time.monotonic()
        sent, recv = self._counters()
        elapsed = max(0.001, now - self.last_time)
        delta_sent = max(0, sent - self.last_sent)
        delta_recv = max(0, recv - self.last_recv)
        self.upload_speed = int(delta_sent / elapsed)
        self.download_speed = int(delta_recv / elapsed)
        self.peak_upload_speed = max(self.peak_upload_speed, self.upload_speed)
        self.peak_download_speed = max(self.peak_download_speed, self.download_speed)
        self.last_sent = sent
        self.last_recv = recv
        self.last_time = now
        if self.active:
            self.session_upload += delta_sent
            self.session_download += delta_recv
            self._add_usage(delta_sent, delta_recv)
        self.speed_points.append({"up": self.upload_speed, "down": self.download_speed})
        self.speed_points = self.speed_points[-60:]
        return self.snapshot()

    def _add_usage(self, upload: int, download: int) -> None:
        date = datetime.now(UTC)
        day_key = date.strftime("%Y-%m-%d")
        week_key = f"{date.isocalendar().year}-W{date.isocalendar().week:02d}"
        month_key = date.strftime("%Y-%m")
        for bucket_name, key in (("daily", day_key), ("weekly", week_key), ("monthly", month_key)):
            bucket = self.storage[bucket_name].setdefault(key, {"upload": 0, "download": 0})
            bucket["upload"] += upload
            bucket["download"] += download
        self.storage["lifetime_upload"] += upload
        self.storage["lifetime_download"] += download

    def snapshot(self) -> dict[str, Any]:
        duration = int(time.monotonic() - self.started_at) if self.active and self.started_at else 0
        return {
            "active": self.active,
            "uploadSpeed": self.upload_speed,
            "downloadSpeed": self.download_speed,
            "uploadSpeedText": f"{format_bytes(self.upload_speed)}/s",
            "downloadSpeedText": f"{format_bytes(self.download_speed)}/s",
            "peakUploadSpeed": self.peak_upload_speed,
            "peakDownloadSpeed": self.peak_download_speed,
            "peakUploadSpeedText": f"{format_bytes(self.peak_upload_speed)}/s",
            "peakDownloadSpeedText": f"{format_bytes(self.peak_download_speed)}/s",
            "sessionUpload": self.session_upload,
            "sessionDownload": self.session_download,
            "sessionUploadText": format_bytes(self.session_upload),
            "sessionDownloadText": format_bytes(self.session_download),
            "sessionTotalText": format_bytes(self.session_upload + self.session_download),
            "duration": duration,
            "durationText": _format_duration(duration),
            "lifetimeUploadText": format_bytes(self.storage["lifetime_upload"]),
            "lifetimeDownloadText": format_bytes(self.storage["lifetime_download"]),
            "monthlyUsageText": format_bytes(sum(v["upload"] + v["download"] for v in self.storage["monthly"].values())),
            "speedPoints": list(self.speed_points),
            "daily": _series(self.storage["daily"], 14),
            "weekly": _series(self.storage["weekly"], 8),
            "monthly": _series(self.storage["monthly"], 12),
        }


def _series(bucket: dict[str, dict[str, int]], limit: int) -> list[dict[str, Any]]:
    items = sorted(bucket.items())[-limit:]
    return [{"label": key, "total": value["upload"] + value["download"]} for key, value in items]


def _format_duration(seconds: int) -> str:
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"
