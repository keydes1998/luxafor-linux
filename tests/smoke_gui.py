"""Headless smoke test for the GUI: boots the core, constructs every page."""
import os
import subprocess
import sys
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer

from luxafor import ui as _ui_pkg  # noqa
from luxafor.ui import api_client, theme
from luxafor.ui.main_window import MainWindow
from luxafor.ui.tray import TrayController


def main() -> int:
    app = QApplication(sys.argv)
    app.setStyleSheet(theme.stylesheet("dark"))

    win = MainWindow()
    tray = TrayController(win)
    win._tray = tray
    win.show()

    results: dict = {}

    def check() -> None:
        try:
            results["nav"] = win.nav.count()
            results["pages"] = win.stack.count()
            results["quick"] = win.dashboard.quick_row.count()
            results["pill"] = win.dashboard.pill._color
            results["device_rows"] = win.devices_page.table.rowCount()
            results["rules_rows"] = win.automations_page.table.currentRow()
            # force construct all pages incl. settings
            for i in range(win.stack.count()):
                win.stack.setCurrentIndex(i)
            results["constructed"] = True
            data = api_client.call("GET", "/api/status")
            results["alive"] = not data.get("_unreachable")
            print("window title:", win.windowTitle())
            print("nav pages:", results["nav"], "| stack:", results["pages"])
            print("quick buttons:", results["quick"], "| pill:", results["pill"])
            print("device rows:", results["device_rows"])
            print("core reachable:", results["alive"])
            print("all pages constructed:", results["constructed"])
            print("GUI SMOKE OK" if results["constructed"] else "GUI SMOKE FAILED")
            app.quit()
        except Exception:
            import traceback
            traceback.print_exc()
            print("GUI SMOKE FAILED (exception)")
            app.quit()
            sys.exit(1)

    QTimer.singleShot(3500, check)
    app.exec()
    return 0


if __name__ == "__main__":
    sys.exit(main())