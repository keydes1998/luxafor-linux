"""Settings page: autostart, background behavior, appearance, logging."""
from __future__ import annotations

import os
import shutil
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QComboBox, QFormLayout, QHBoxLayout, QLabel, QMessageBox, QPushButton,
    QScrollArea, QSpinBox, QVBoxLayout, QWidget,
)

from luxafor.ui import api_client
from luxafor.ui.i18n import tr
from luxafor.ui.widgets import Card, ToggleRow


def user_home() -> Path:
    return Path.home()


def write_autostart(enable: bool, start_minimized: bool = False) -> str:
    """Manages ~/.config/autostart/luxafor-gui.desktop (XDG autostart)."""
    autostart_dir = Path(os.environ.get("XDG_CONFIG_HOME", user_home() / ".config")) / "autostart"
    path = autostart_dir / "luxafor-gui.desktop"
    try:
        if enable:
            autostart_dir.mkdir(parents=True, exist_ok=True)
            gui_exe = shutil.which("lx-gui") or "lx-gui"
            args = f"{gui_exe} --tray" if start_minimized else gui_exe
            path.write_text(
                "[Desktop Entry]\nType=Application\n"
                "Name=Luxafor\nComment=Luxafor LED control\n"
                f"Exec={args}\nTerminal=false\nNoDisplay=false\nCategories=Utility;\n")
            return str(path)
        path.unlink(missing_ok=True)
        return ""
    except OSError as exc:
        return f"Fehler: {exc}"


def check_core_autostart() -> bool:
    """True when the systemd user unit exists (installed by install.sh)."""
    base = Path(os.environ.get("XDG_CONFIG_HOME", user_home() / ".config"))
    return (base / "systemd/user/luxafor-core.service").exists()


def _systemctl(action: str, page) -> None:
    import subprocess
    try:
        subprocess.run(["systemctl", "--user", action, "luxafor-core"],
                       check=False, timeout=15)
    except (OSError, subprocess.TimeoutExpired):
        pass
    page.refresh()


class SettingsPage(QWidget):
    def __init__(self, main_window) -> None:
        super().__init__()
        self.main_window = main_window
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(16)

        title = QLabel(tr("Settings"))
        title.setObjectName("h1")
        root.addWidget(title)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        inner = QWidget()
        lay = QVBoxLayout(inner)
        lay.setSpacing(14)
        scroll.setWidget(inner)
        root.addWidget(scroll)

        # --- general behavior ----------------------------------------------
        c1 = Card("Verhalten")
        form = QFormLayout()
        self.tg_autostart = ToggleRow(tr("autostart"))
        self.tg_minimized = ToggleRow(tr("start_minimized"))
        self.tg_tray = ToggleRow(tr("close_to_tray"))
        self.tg_notifications = ToggleRow(tr("notifications"))
        for row in (self.tg_autostart, self.tg_minimized, self.tg_tray, self.tg_notifications):
            form.addRow(row)
        self.tg_autostart.checkbox.toggled.connect(self._save_autostart)
        self.tg_autostart.checkbox.toggled.connect(lambda _: setattr(self.tg_autostart, '_flag_touched', True))
        self.tg_minimized.checkbox.toggled.connect(self._save_autostart)
        c1.lay.addLayout(form)
        self.lbl_core_autostart = QLabel(
            "Hintergrunddienst (systemd --user): " +
            ("installiert ✓" if check_core_autostart() else
             "nicht installiert — siehe scripts/install.sh"))
        self.lbl_core_autostart.setObjectName("muted")
        c1.add(self.lbl_core_autostart)
        lay.addWidget(c1)

        # --- background service -------------------------------------------------
        cs = Card("Hintergrunddienst")
        form_svc = QFormLayout()
        row_svc = QHBoxLayout()
        self.btn_core_start = QPushButton("Starten")
        self.btn_core_stop = QPushButton("Stoppen")
        self.btn_core_restart = QPushButton("Neustart")
        for b in (self.btn_core_start, self.btn_core_stop, self.btn_core_restart):
            row_svc.addWidget(b)
        row_svc.addStretch(1)
        form_svc.addRow(row_svc)
        self.lbl_core_status = QLabel("—")
        self.lbl_core_status.setObjectName("muted")
        form_svc.addRow("Status", self.lbl_core_status)
        self.tg_stop_on_quit = ToggleRow("Beim Beenden der GUI den Dienst stoppen")
        form_svc.addRow(self.tg_stop_on_quit)
        cs.lay.addLayout(form_svc)
        lbl_hint = QLabel("Hinweis: Ohne Dienst steuert nur die GUI — Integrationen und "
                          "Regeln laufen dann nicht. Standard: dauerhaft im Hintergrund.")
        lbl_hint.setObjectName("muted")
        lbl_hint.setWordWrap(True)
        cs.add(lbl_hint)
        lay.addWidget(cs)
        self.btn_core_start.clicked.connect(lambda: _systemctl("start", self))
        self.btn_core_stop.clicked.connect(lambda: _systemctl("stop", self))
        self.btn_core_restart.clicked.connect(lambda: _systemctl("restart", self))
        self.tg_stop_on_quit.checkbox.toggled.connect(self._save_quit_setting)

        # --- sync / engine -----------------------------------------------------
        c2 = Card("Synchronisierung & Automatik")
        form2 = QFormLayout()
        self.interval = QSpinBox()
        self.interval.setRange(20, 3600)
        self.interval.setSuffix(" s")
        form2.addRow(tr("interval"), self.interval)
        self.sim_mode = QComboBox()
        self.sim_mode.addItem("Auto (ohne Hardware simulieren)", "auto")
        self.sim_mode.addItem("Erzwungen", "force")
        self.sim_mode.addItem("Aus", "off")
        form2.addRow(tr("simulator"), self.sim_mode)
        self.loglevel = QComboBox()
        for lvl in ("DEBUG", "INFO", "WARNING", "ERROR"):
            self.loglevel.addItem(lvl.lower(), lvl)
        form2.addRow(tr("log_level"), self.loglevel)
        c2.lay.addLayout(form2)
        save_row = QHBoxLayout()
        self.btn_save = QPushButton(tr("save"))
        self.btn_save.setObjectName("primary")
        save_row.addStretch(1)
        save_row.addWidget(self.btn_save)
        save_row.addStretch(1)
        c2.lay.addLayout(save_row)
        lay.addWidget(c2)

        # --- appearance ----------------------------------------------------------
        c3 = Card(tr("theme") + " / " + tr("language"))
        form3 = QFormLayout()
        self.theme = QComboBox()
        self.theme.addItem("Dunkel", "dark")
        self.theme.addItem("Hell", "light")
        form3.addRow(tr("theme"), self.theme)
        self.lang = QComboBox()
        self.lang.addItem("Deutsch", "de")
        self.lang.addItem("English", "en")
        form3.addRow(tr("language"), self.lang)
        c3.lay.addLayout(form3)
        save3 = QHBoxLayout()
        self.btn_save_ui = QPushButton(tr("save"))
        self.btn_save_ui.setObjectName("primary")
        save3.addStretch(1)
        save3.addWidget(self.btn_save_ui)
        save3.addStretch(1)
        c3.lay.addLayout(save3)
        lay.addWidget(c3)

        self.btn_save.clicked.connect(self._save_core)
        self.btn_save_ui.clicked.connect(self._save_ui)

        self.timer = QTimer(self)
        self.timer.setInterval(8000)
        self.timer.timeout.connect(self.refresh)
        self.timer.start()
        self.refresh()

    def refresh(self) -> None:
        api_client.run_async(lambda: api_client.call("GET", "/api/settings"),
                             self._apply_settings)
        # Dienst-Status + Quit-Setting aktualisieren
        import subprocess
        try:
            res = subprocess.run(["systemctl", "--user", "is-active", "luxafor-core"],
                                 capture_output=True, text=True, timeout=5)
            state = (res.stdout or "").strip() or "unbekannt"
            self.lbl_core_status.setText(state)
            self.btn_core_start.setEnabled(state != "active")
            self.btn_core_stop.setEnabled(state == "active")
        except (OSError, subprocess.TimeoutExpired):
            self.lbl_core_status.setText("systemctl nicht verfügbar")
        if not getattr(self.tg_stop_on_quit, "_loaded_once", False):
            self.tg_stop_on_quit._loaded_once = True

    def _save_quit_setting(self, checked: bool) -> None:
        payload = {"ui.stop_core_on_quit": "true" if checked else "false"}
        api_client.run_async(lambda p=payload: api_client.call("PUT", "/api/settings", p),
                             lambda d: None)

    def _apply_settings(self, data: dict) -> None:
        if data.get("_unreachable"):
            return
        if not self.interval.hasFocus():
            self.interval.setValue(int(data.get("sync.interval_seconds", 60) or 60))
        idx = self.sim_mode.findData(str(data.get("hardware.simulator", "auto")))
        self.sim_mode.setCurrentIndex(max(0, idx))
        idx = self.loglevel.findData(str(data.get("log.level", "INFO")))
        self.loglevel.setCurrentIndex(max(0, idx))
        self.theme.setCurrentIndex(1 if str(data.get("ui.theme")) == "light" else 0)
        idx = self.lang.findData(str(data.get("ui.language", "de")))
        self.lang.setCurrentIndex(max(0, idx))
        # local (Qt) settings live in the same store
        self.tg_tray.setChecked(str(data.get("ui.close_to_tray", "true")).lower() == "true")
        self.tg_minimized.setChecked(str(data.get("ui.start_minimized", "false")).lower() == "true")
        self.tg_notifications.setChecked(str(data.get("ui.notify_on_change", "true")).lower() == "true")
        self.tg_stop_on_quit.setChecked(str(data.get("ui.stop_core_on_quit", "false")).lower() == "true")
        # autostart file state (local fs)
        autostart = Path(os.environ.get("XDG_CONFIG_HOME", user_home() / ".config")) / "autostart" / "luxafor-gui.desktop"
        if not getattr(self.tg_autostart, '_user_touched', False):
            self.tg_autostart.setChecked(autostart.exists())

    def _save_autostart(self, _checked=None) -> None:
        self.tg_autostart._user_touched = True
        res = write_autostart(self.tg_autostart.isChecked(),
                              self.tg_minimized.isChecked())
        if res.startswith("Fehler"):
            QMessageBox.warning(self, tr("autostart"), res)

    def _save_core(self) -> None:
        payload = {
            "sync.interval_seconds": str(self.interval.value()),
            "hardware.simulator": self.sim_mode.currentData(),
            "log.level": self.loglevel.currentData(),
            "ui.close_to_tray": str(self.tg_tray.isChecked()).lower(),
            "ui.start_minimized": str(self.tg_minimized.isChecked()).lower(),
            "ui.notify_on_change": str(self.tg_notifications.isChecked()).lower(),
        }
        api_client.run_async(lambda p=payload: api_client.call("PUT", "/api/settings", p),
                             lambda d: QMessageBox.information(
                                 self, tr("save"), "Gespeichert."))

    def _save_ui(self) -> None:
        def apply_result(_):
            self.main_window.apply_theme(self.theme.currentData(), self.lang.currentData())
            QMessageBox.information(self, tr("save"), tr("theme") + " ✓")

        payload = {"ui.theme": self.theme.currentData(), "ui.language": self.lang.currentData()}
        api_client.run_async(lambda p=payload: api_client.call("PUT", "/api/settings", p),
                             apply_result)