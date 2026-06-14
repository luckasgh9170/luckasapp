from __future__ import annotations

import asyncio
import threading
from collections.abc import Coroutine
from typing import Any


class AsyncRunner:
    def __init__(self) -> None:
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()
        self._closed = False

    def _run(self) -> None:
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def submit(self, coro: Coroutine[Any, Any, Any]):
        if self._closed:
            raise RuntimeError("AsyncRunner is closed")
        return asyncio.run_coroutine_threadsafe(coro, self.loop)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self.loop.call_soon_threadsafe(self.loop.stop)
        self.thread.join(timeout=2)
