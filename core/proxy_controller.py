from __future__ import annotations

import platform
from dataclasses import dataclass

if platform.system() == "Windows":
    import ctypes
    import winreg


@dataclass(frozen=True)
class SystemProxyState:
    enabled: bool
    server: str = ""


class ProxyController:
    def __init__(self) -> None:
        self.mode = "direct"

    def set_mode(self, mode: str, host: str = "127.0.0.1", port: int = 10809) -> str:
        self.mode = mode
        if platform.system() != "Windows":
            return f"{mode} mode stored. System proxy automation is Windows-focused."
        if mode in {"global", "proxy"}:
            self.enable_system_proxy(host, port)
            return f"System proxy enabled at {host}:{port}"
        if mode == "direct":
            self.disable()
            return "System proxy disabled"
        return f"{mode} mode stored."

    def enable_system_proxy(self, host: str, port: int) -> None:
        if platform.system() != "Windows":
            return
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Internet Settings",
            0,
            winreg.KEY_SET_VALUE,
        ) as key:
            winreg.SetValueEx(key, "ProxyEnable", 0, winreg.REG_DWORD, 1)
            winreg.SetValueEx(key, "ProxyServer", 0, winreg.REG_SZ, f"http={host}:{port};https={host}:{port};socks={host}:{port}")
        _notify_proxy_changed()

    def disable(self) -> str:
        self.mode = "direct"
        if platform.system() == "Windows":
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Internet Settings",
                0,
                winreg.KEY_SET_VALUE,
            ) as key:
                winreg.SetValueEx(key, "ProxyEnable", 0, winreg.REG_DWORD, 0)
            _notify_proxy_changed()
        return "Proxy disabled"

    def status(self) -> SystemProxyState:
        if platform.system() != "Windows":
            return SystemProxyState(enabled=False)
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Internet Settings",
        ) as key:
            enabled = bool(winreg.QueryValueEx(key, "ProxyEnable")[0])
            try:
                server = str(winreg.QueryValueEx(key, "ProxyServer")[0])
            except FileNotFoundError:
                server = ""
        return SystemProxyState(enabled=enabled, server=server)


def _notify_proxy_changed() -> None:
    if platform.system() != "Windows":
        return
    INTERNET_OPTION_SETTINGS_CHANGED = 39
    INTERNET_OPTION_REFRESH = 37
    ctypes.windll.Wininet.InternetSetOptionW(0, INTERNET_OPTION_SETTINGS_CHANGED, 0, 0)
    ctypes.windll.Wininet.InternetSetOptionW(0, INTERNET_OPTION_REFRESH, 0, 0)
