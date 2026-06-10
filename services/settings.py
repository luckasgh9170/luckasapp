from __future__ import annotations

from pathlib import Path
from typing import Any

import orjson


DEFAULT_SETTINGS: dict[str, Any] = {
    "language": "English",
    "theme": "dark",
    "startup_behavior": "normal",
    "auto_start": False,
    "dns_server": "1.1.1.1",
    "ipv6": True,
    "dns_cache": True,
    "enable_socks": True,
    "enable_http": True,
    "socks_port": 10808,
    "http_port": 10809,
    "enable_tun": False,
    "kill_switch": False,
    "dns_leak_protection": True,
    "auto_reconnect": True,
    "auto_connect": False,
    "smart_connect": True,
    "fastest_node_selection": True,
    "validation_workers": 4,
    "validation_timeout": 8,
    "retry_count": 1,
    "auto_recheck": False,
    "auto_update": True,
    "beta_channel": False,
    "github_owner": "luckasgh9170",
    "github_repository": "luckasapp",
    "github_branch": "main",
    "update_version_url": "https://raw.githubusercontent.com/luckasgh9170/luckasapp/main/version.json",
    "github_releases_url": "https://github.com/luckasgh9170/luckasapp/releases",
    "github_distribution_base_url": "",
    "auto_sync": False,
    "sync_interval": 30,
    "background_sync": False,
    "download_folder": "downloads",
    "cache_size_mb": 512,
    "new_update_notifications": True,
    "sync_complete_notifications": True,
    "error_notifications": True,
    "encrypted_storage": False,
    "secure_config_storage": True,
    "protected_credentials": True,
}


class SettingsStore:
    def __init__(self, root: Path) -> None:
        self.path = root / "cache" / "settings.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._settings = self._load()

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            self.path.write_bytes(orjson.dumps(DEFAULT_SETTINGS, option=orjson.OPT_INDENT_2))
            return dict(DEFAULT_SETTINGS)
        try:
            data = orjson.loads(self.path.read_bytes())
            merged = dict(DEFAULT_SETTINGS)
            merged.update(data)
            return merged
        except Exception:
            return dict(DEFAULT_SETTINGS)

    def all(self) -> dict[str, Any]:
        return dict(self._settings)

    def get(self, key: str, default: Any = None) -> Any:
        return self._settings.get(key, default)

    def set(self, key: str, value: Any) -> dict[str, Any]:
        if key not in DEFAULT_SETTINGS:
            return self.all()
        self._settings[key] = value
        self.path.write_bytes(orjson.dumps(self._settings, option=orjson.OPT_INDENT_2))
        return self.all()
