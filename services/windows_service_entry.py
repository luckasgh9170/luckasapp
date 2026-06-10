from __future__ import annotations

import asyncio
from pathlib import Path
from threading import Event

import servicemanager
import win32event
import win32service
import win32serviceutil

from services.background_sync import BackgroundServiceRuntime
from services.service_state import ServiceStateStore


ROOT = Path(__file__).resolve().parents[1]


class LuckasAppWindowsService(win32serviceutil.ServiceFramework):
    _svc_name_ = "LuckasAppBackgroundService"
    _svc_display_name_ = "LuckasApp Background Service"
    _svc_description_ = "Synchronizes LuckasApp nodes, maintains local cache, and runs background health checks."

    def __init__(self, args) -> None:
        super().__init__(args)
        self.stop_event_handle = win32event.CreateEvent(None, 0, 0, None)
        self.stop_event = Event()
        self.state = ServiceStateStore(ROOT)

    def SvcStop(self) -> None:
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        self.stop_event.set()
        win32event.SetEvent(self.stop_event_handle)
        self.state.write(status="Stopped")

    def SvcDoRun(self) -> None:
        self.ReportServiceStatus(win32service.SERVICE_RUNNING)
        servicemanager.LogInfoMsg("LuckasApp Background Service started")
        self.state.write(status="Running")
        self.state.log("service", "Windows Service entrypoint started")
        try:
            asyncio.run(BackgroundServiceRuntime(ROOT).run_forever(self.stop_event))
        except Exception as exc:
            self.state.write(status="Error", last_error=str(exc))
            self.state.log("service_error", str(exc))
            servicemanager.LogErrorMsg(str(exc))
