from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QTimer, QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine

from ui.bridge import AppBridge


SIZES = [(640, 720), (900, 700), (1220, 780), (1600, 900)]
PAGES = [
    "Dashboard",
    "Servers",
    "Scan",
    "Favorites",
    "Statistics",
    "Settings",
]


def main() -> int:
    app = QGuiApplication([])
    root_path = ROOT
    for width, height in SIZES:
        engine = QQmlApplicationEngine()
        bridge = AppBridge(root_path)
        engine.rootContext().setContextProperty("appBridge", bridge)
        engine.load(QUrl.fromLocalFile(str(root_path / "ui" / "Main.qml")))
        roots = engine.rootObjects()
        if not roots:
            print(f"FAIL {width}x{height}: QML root not loaded")
            return 1
        window = roots[0]
        window.setWidth(width)
        window.setHeight(height)
        for page in PAGES:
            window.setProperty("currentPage", page)
            app.processEvents()
        print(f"OK {width}x{height}")
        window.close()
        engine.deleteLater()
    QTimer.singleShot(0, app.quit)
    app.exec()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
