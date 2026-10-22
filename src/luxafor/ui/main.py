"""PySide6 application bootstrap: core launcher, theme, tray, notifications."""
from __future__ import annotations

import base64
import json
import sys

from PySide6.QtCore import QThread, Signal as QtSignal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMessageBox

from luxafor import __version__
from luxafor.core import config
from luxafor.ui import api_client, theme
from luxafor.ui.main_window import MainWindow
from luxafor.ui.tray import TrayController, make_icon


def maybe_stop_core(settings: dict) -> None:
    """Stoppt den Hintergrunddienst, wenn 'Bei Beenden stoppen' aktiv ist."""
    if str(settings.get("ui.stop_core_on_quit", "false")).lower() != "true":
        return
    import subprocess
    try:
        subprocess.run(["systemctl", "--user", "stop", "luxafor-core"],
                       check=False, timeout=15)
    except (OSError, subprocess.TimeoutExpired):
        pass


class SSEWorker(QThread):
    """Streams the core event bus; forwards raw payloads to the GUI thread."""
    event_received = QtSignal(dict)

    def run(self) -> None:
        import urllib.request
        try:
            resp = urllib.request.urlopen(api_client.api_base() + "/api/events")
        except Exception:
            return
        self._resp = resp
        current_event = ""
        try:
            for raw in resp:
                if self.isInterruptionRequested():
                    break
                line = raw.decode(errors="replace").strip()
                if line.startswith("event: "):
                    current_event = line[7:].strip()
                elif line.startswith("data: "):
                    try:
                        payload = json.loads(line[6:])
                    except json.JSONDecodeError:
                        continue
                    payload.setdefault("_kind", current_event)
                    self.event_received.emit(payload)
        except Exception:
            return
        finally:
            try:
                resp.close()
            except Exception:
                pass

    def stop(self) -> None:
        self.requestInterruption()
        try:
            self._resp.close()
        except Exception:
            pass


def main() -> None:
    autostart_tray = "--tray" in sys.argv

    # GUI-Log (Abstürze/Kontext sichtbar machen) + segfault-faulthandler
    from luxafor.core import logging_setup as _ls
    _ls.setup_logging((api_client.call("GET", "/api/settings", timeout=3) or {}).get(
        "log.level", "INFO"), console=False)
    _log = _ls.get_logger("gui")
    _log.info("GUI startet")
    try:
        import faulthandler
        faulthandler.enable(open(config.LOG_PATH, "a"))
    except Exception:
        pass

    app = QApplication(sys.argv)
    app.setApplicationName("Luxafor")
    app.setOrganizationName("luxafor")
    app.setApplicationVersion(__version__)
    app.setWindowIcon(QIcon(make_icon()))
    app.setDesktopFileName("luxafor")
    app.setQuitOnLastWindowClosed(False)

    # wait for / start the core daemon
    if not api_client.core_running():
        try:
            if not api_client.ensure_core():
                QMessageBox.warning(
                    None, "Luxafor",
                    "Der Hintergrunddienst ist nicht erreichbar.\n\nManuell starten mit: "
                    "systemctl --user start luxafor-core  oder  lx-core")
        except RuntimeError:
            pass

    try:
        settings = api_client.call("GET", "/api/settings", timeout=4)
    except Exception:
        settings = {}
    theme_name = str(settings.get("ui.theme", "dark"))
    language = str(settings.get("ui.language", "de"))

    win = MainWindow()
    tray = TrayController(win)
    win._tray = tray
    app.setStyleSheet(theme.stylesheet(theme_name))
    win.apply_theme(theme_name, language, initial=True)

    poller = SSEWorker(win)
    poller.event_received.connect(win.on_state_event)
    app.aboutToQuit.connect(poller.stop)
    app.aboutToQuit.connect(lambda: maybe_stop_core(settings))

    if autostart_tray or str(settings.get("ui.start_minimized", "false")).lower() == "true":
        win.hide()
    else:
        win.show()

    poller.start()
    exit_code = app.exec()
    _log.info("GUI beendet (code %s)", exit_code)
    # sauberer Thread-Stopp, damit Qt beim Beenden nicht crashed
    poller.stop()
    if not poller.wait(3000):
        poller.terminate()
    sys.exit(exit_code)


if __name__ == "__main__":
    main()