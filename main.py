from __future__ import annotations

import os
import sys
import logging
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def configure_logging() -> None:
    log_dir = ROOT / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(log_dir / "app.log", encoding="utf-8"),
            logging.StreamHandler(sys.stderr),
        ],
    )


def main() -> int:
    configure_logging()
    os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Fusion")
    try:
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QGuiApplication
        from PySide6.QtQml import QQmlApplicationEngine
    except ImportError as exc:
        print("PySide6 is not installed. Run: pip install -r requirements.txt")
        print(f"Import error: {exc}")
        return 1

    from ui.bridge import AppBridge

    app = QGuiApplication(sys.argv)
    engine = QQmlApplicationEngine()

    bridge = AppBridge(ROOT)
    engine.rootContext().setContextProperty("appBridge", bridge)
    engine.load(QUrl.fromLocalFile(str(ROOT / "ui" / "Main.qml")))

    if not engine.rootObjects():
        return 1

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
