from __future__ import annotations

import platform


class ProxyController:
    def __init__(self) -> None:
        self.mode = "direct"

    def set_mode(self, mode: str) -> str:
        self.mode = mode
        if platform.system() != "Windows":
            return f"{mode} mode stored. System proxy automation is Windows-focused."
        return f"{mode} mode stored. Registry proxy wiring can be enabled in settings."

    def disable(self) -> str:
        self.mode = "direct"
        return "Proxy disabled"
