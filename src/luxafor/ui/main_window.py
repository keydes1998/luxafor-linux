"""Main window with sidebar navigation and page stack."""
from __future__ import annotations

from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QAction, QIcon, QKeySequence, QColor
from PySide6.QtWidgets import (
    QApplication, QFrame, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QMainWindow, QMessageBox, QStackedWidget, QVBoxLayout, QWidget,
)

from luxafor.ui import api_client, theme
from luxafor.ui.i18n import set_language, tr
from luxafor.ui.pages.dashboard import DashboardPage
from luxafor.ui.pages.devices import DevicesPage
from luxafor.ui.pages.integrations import IntegrationsPage
from luxafor.ui.pages.automations import AutomationsPage
from luxafor.ui.pages.profiles import ProfilesPage
from luxafor.ui.pages.settings import SettingsPage
from luxafor.ui.pages.diagnostics import DiagnosticsPage

PAGE_KEYS = [
    ("dashboard", "Dashboard", None),
    ("devices", "Devices", None),
    ("integrations", "Integrations", "1"),
    ("automations", "Automations", "⚙"),
    ("profiles", "Profiles", "◱"),
    ("diagnostics", "Diagnostics", "✚"),
    ("settings", "Settings", "✱"),
]


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Luxafor")
        self.setMinimumSize(QSize(980, 660))
        self._last_state_payload = {}
        self._notifications_enabled = True
        self._close_to_tray = True

        central = QWidget()
        lay = QHBoxLayout(central)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self.setCentralWidget(central)

        # sidebar -------------------------------------------------------------
        sidebar = QWidget()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(200)
        sl = QVBoxLayout(sidebar)
        sl.setContentsMargins(0, 0, 0, 0)
        brand = QLabel("LUXAFOR")
        brand.setObjectName("brand")
        sl.addWidget(brand)
        self.nav = QListWidget()
        self.nav.setObjectName("nav")
        self.nav.setFrameShape(QListWidget.NoFrame)
        for key, title, icon in PAGE_KEYS:
            item = QListWidgetItem(f"  {icon or ''}  {tr(title)}".strip())
            item.setData(Qt.UserRole, key)
            self.nav.addItem(item)
        self.nav.currentRowChanged.connect(self._navigate)
        sl.addWidget(self.nav, 1)
        self.lbl_version = QLabel("")
        self.lbl_version.setObjectName("muted")
        self.lbl_version.setAlignment(Qt.AlignCenter)
        self.lbl_version.setContentsMargins(0, 0, 0, 12)
        sl.addWidget(self.lbl_version)
        lay.addWidget(sidebar)

        line = QFrame()
        line.setFixedWidth(1)
        line.setStyleSheet("background:#242834;")
        lay.addWidget(line)

        # content stack ----------------------------------------------------------
        self.stack = QStackedWidget()
        self.stack.setObjectName("content")
        self.dashboard = DashboardPage()
        self.devices_page = DevicesPage()
        self.integrations_page = IntegrationsPage()
        self.automations_page = AutomationsPage()
        self.profiles_page = ProfilesPage()
        self.settings_page = SettingsPage(self)
        self.diagnostics_page = DiagnosticsPage()
        self.stack.addWidget(self.dashboard)
        self.stack.addWidget(self.devices_page)
        self.stack.addWidget(self.integrations_page)
        self.stack.addWidget(self.automations_page)
        self.stack.addWidget(self.profiles_page)
        self.stack.addWidget(self.diagnostics_page)
        self.stack.addWidget(self.settings_page)
        lay.addWidget(self.stack, 1)

        self.nav.setCurrentRow(0)
        self._settings_init_done = False
        self._load_initial_settings()

    # -- navigation ------------------------------------------------------------
    def _navigate(self, row: int) -> None:
        key = PAGE_KEYS[row][0] if 0 <= row < len(PAGE_KEYS) else "dashboard"
        index = {"dashboard": 0, "devices": 1, "integrations": 2, "automations": 3,
                 "profiles": 4, "diagnostics": 5, "settings": 6}[key]
        self.stack.setCurrentIndex(index)

    def go_to(self, key: str) -> None:
        for i, (k, _, _) in enumerate(PAGE_KEYS):
            if k == key:
                self.nav.setCurrentRow(i)
                return

    # -- settings bootstrap ------------------------------------------------------
    def _load_initial_settings(self) -> None:
        def apply(data: dict) -> None:
            if isinstance(data, dict):
                self.apply_theme(str(data.get("ui.theme", "dark")),
                                 str(data.get("ui.language", "de")),
                                 initial=True)
                self._notifications_enabled = str(
                    data.get("ui.notify_on_change", "true")).lower() == "true"
                self._close_to_tray = str(
                    data.get("ui.close_to_tray", "true")).lower() == "true"
                ver = data.get("version") or ""
                self.lbl_version.setText(f"v{ver}" if ver else "")
                self._settings_init_done = True
        api_client.run_async(lambda: api_client.call("GET", "/api/status"), apply)

    def apply_theme(self, theme_name: str, lang: str = "de", initial: bool = False) -> None:
        set_language(lang)
        app = QApplication.instance()
        if app:
            app.setStyleSheet(theme.stylesheet(theme_name))
        if not initial:
            # rebuild pages so translated labels refresh
            self.stack.removeWidget(self.dashboard)
            self.stack.removeWidget(self.devices_page)
            self.stack.removeWidget(self.integrations_page)
            self.stack.removeWidget(self.automations_page)
            self.stack.removeWidget(self.profiles_page)
            self.stack.removeWidget(self.diagnostics_page)
            self.stack.removeWidget(self.settings_page)
            for w in (self.dashboard, self.devices_page, self.integrations_page,
                      self.automations_page, self.profiles_page, self.diagnostics_page,
                      self.settings_page):
                w.deleteLater()
            self.dashboard = DashboardPage()
            self.devices_page = DevicesPage()
            self.integrations_page = IntegrationsPage()
            self.automations_page = AutomationsPage()
            self.profiles_page = ProfilesPage()
            self.diagnostics_page = DiagnosticsPage()
            self.settings_page = SettingsPage(self)
            for idx, page in enumerate([self.dashboard, self.devices_page,
                                        self.integrations_page, self.automations_page,
                                        self.profiles_page, self.diagnostics_page,
                                        self.settings_page]):
                self.stack.addWidget(page)
            row = self.nav.currentRow()
            self.stack.setCurrentIndex(max(0, row))
        for i, (key, title, icon) in enumerate(PAGE_KEYS):
            self.nav.item(i).setText(f"  {icon or ''}  {tr(title)}".strip())

    # -- state change notifications --------------------------------------------------
    def on_state_event(self, payload: dict) -> None:
        """Called by the SSE poller when any core event occurs."""
        kind = payload.get("_kind", "")
        if kind == "auth_url":
            import webbrowser
            webbrowser.open(str(payload.get("url", "")))
        if kind == "state":
            self._last_state_payload = payload
            if getattr(self, "_tray", None) and self._tray.tray_available:
                if self._tray.tray:
                    self._tray.update_icon(payload.get("color"))
                if self._notifications_enabled:
                    self._tray.show_message(
                        "Luxafor", f"Status: {payload.get('label', '')} ({payload.get('color', '')})")
        self.dashboard.refresh()

    def refresh_all(self) -> None:
        self.dashboard.refresh()
        self.devices_page.refresh()

    # -- close behavior -----------------------------------------------------------------
    def closeEvent(self, ev) -> None:  # noqa: N802
        if self._close_to_tray and getattr(self, "_tray", None) and self._tray.tray_available:
            ev.ignore()
            self.hide()
            self._tray.show_message("Luxafor", "Läuft im Hintergrund weiter.")
        else:
            ev.accept()