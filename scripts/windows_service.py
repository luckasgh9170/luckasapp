from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

try:
    import servicemanager
    import win32serviceutil
except ImportError as exc:  # pragma: no cover
    raise SystemExit("pywin32 is required. Run: python -m pip install pywin32") from exc

from services.windows_service_entry import LuckasAppWindowsService

LuckasAppWindowsService._exe_name_ = sys.executable
LuckasAppWindowsService._exe_args_ = f'"{Path(__file__).resolve()}"'


def main() -> None:
    if len(sys.argv) == 1:
        servicemanager.Initialize()
        servicemanager.PrepareToHostSingle(LuckasAppWindowsService)
        servicemanager.StartServiceCtrlDispatcher()
    else:
        win32serviceutil.HandleCommandLine(LuckasAppWindowsService)


if __name__ == "__main__":
    main()
