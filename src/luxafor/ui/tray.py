"""System tray integration with quick status actions.

GNOME (Wayland) shows tray icons only with the AppIndicator extension;
the core daemon keeps running regardless, and the GUI works as usual.
"""
from __future__ import annotations

import base64

from PySide6.QtGui import QAction, QPainter, QPixmap, QColor
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMenu, QSystemTrayIcon, QApplication

from luxafor.ui import api_client
from luxafor.ui.i18n import tr


def make_icon(color: str | None = None) -> "QPixmap":
    """Rounded LED-like icon; optionally tinted with the current color."""
    pix = QPixmap(64, 64)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)
    c = QColor(color) if color and color.startswith("#") else QColor("#2979FF")
    p.setBrush(c)
    p.setPen(Qt.NoPen)
    p.drawRoundedRect(10, 18, 44, 28, 12, 12)
    p.setBrush(QColor(0, 0, 0, 70))
    p.drawRoundedRect(16, 34, 32, 8, 4, 4)
    p.end()
    return pix


class TrayController:
    def __init__(self, main_window) -> None:
        self.main_window = main_window
        self.tray_available = QSystemTrayIcon.isSystemTrayAvailable()
        self.tray = None
        self.menu = None
        if not self.tray_available:
            return
        self.tray = QSystemTrayIcon(make_icon(), main_window)
        self.tray.setToolTip("Luxafor")
        self.menu = QMenu()
        self._build_menu()
        self.tray.setContextMenu(self.menu)
        self.tray.activated.connect(self._on_activated)
        self.tray.show()

    def _build_menu(self) -> None:
        self.menu.clear()
        title = self.menu.addAction("Luxafor")
        title.setEnabled(False)
        self.menu.addSeparator()

        self.state_actions: list[tuple[QAction, str]] = []
        for label, name in [("Verfügbar", "Verfügbar"), ("Beschäftigt", "Beschäftigt"),
                            ("Nicht stören", "Nicht stören"), ("Pause", "Pause")]:
            act = self.menu.addAction(label)
            act.triggered.connect(lambda _=False, n=name: self._set_status(n))
            self.state_actions.append((act, name))
        self.menu.addSeparator()
        self.act_pause = self.menu.addAction(tr("pause_sync"))
        self.act_pause.triggered.connect(self._toggle_pause)
        self.act_off = self.menu.addAction(tr("led_off"))
        self.act_off.triggered.connect(self._turn_off)
        self.act_restore = self.menu.addAction(tr("restore_auto"))
        self.act_restore.triggered.connect(self._restore)
        self.menu.addSeparator()
        self.act_show = self.menu.addAction("Anwendung öffnen")
        self.act_show.triggered.connect(self._show_window)
        self.act_quit = self.menu.addAction("Beenden")
        self.act_quit.triggered.connect(self._really_quit)

    def _on_activated(self, reason) -> None:
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            self._show_window()

    # -- actions -------------------------------------------------------------------
    def _set_status(self, name: str) -> None:
        api_client.run_async(lambda: api_client.call("POST", "/api/status", {"status": name}),
                             lambda d: None)

    def _toggle_pause(self) -> None:
        def step1():
            return api_client.call("GET", "/api/status")
        def step2(res):
            paused = bool(res.get("paused"))
            api_client.run_async(
                lambda p=not paused: api_client.call("POST", "/api/sync/pause", {"paused": p}),
                lambda d: self._rebuild_for_pause(not paused))
        api_client.run_async(step1, step2)

    def _rebuild_for_pause(self, paused: bool) -> None:
        if self.act_pause:
            self.act_pause.setText(tr("resume_sync") if paused else tr("pause_sync"))

    def _turn_off(self) -> None:
        api_client.run_async(lambda: api_client.call("POST", "/api/device/off", {}),
                             lambda d: None)

    def _restore(self) -> None:
        api_client.run_async(lambda: api_client.call("POST", "/api/status/restore", {}),
                             lambda d: None)

    def _show_window(self) -> None:
        w = self.main_window
        w.showNormal()
        w.raise_()
        w.activateWindow()

    def _really_quit(self) -> None:
        """Full quit; stoppt auf Wunsch auch den Hintergrunddienst."""
        self.main_window._close_to_tray = False
        QApplication.instance().quit()

    # -- updates -------------------------------------------------------------------
    def update_icon(self, color: str | None) -> None:
        if self.tray:
            self.tray.setIcon(make_icon(color))

    def show_message(self, title: str, text: str) -> None:
        if self.tray:
            self.tray.showMessage(title, text, QSystemTrayIcon.Information, 3000)