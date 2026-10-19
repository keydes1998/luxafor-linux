"""Integrations page: Microsoft Teams, Outlook, Webhooks, REST API."""
from __future__ import annotations

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QComboBox, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
    QPushButton, QScrollArea, QSpinBox, QVBoxLayout, QWidget, QInputDialog,
    QTableWidget, QTableWidgetItem,
)

from luxafor.ui import api_client
from luxafor.ui.i18n import tr
from luxafor.ui.widgets import Badge, Card, ColorButton, EffectPicker, hline, ToggleRow
from luxafor.ui.teams_setup import TeamsSetupDialog

CONFLICTS = [
    ("teams_wins", "Teams hat Vorrang"),
    ("meeting_wins", "Kalender hat Vorrang"),
    ("teams_after_meeting", "Kalender während Termin, danach Teams"),
]


class IntegrationsPage(QWidget):
    def __init__(self) -> None:
        super().__init__()
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(16)

        title = QLabel(tr("Integrations"))
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
        lay.addWidget(self._teams_card())
        lay.addWidget(self._outlook_card())
        lay.addWidget(self._webhook_card())
        lay.addWidget(self._api_card())
        lay.addStretch(1)

        self.timer = QTimer(self)
        self.timer.setInterval(6000)
        self.timer.timeout.connect(self.refresh)
        self.timer.start()
        self.refresh()

    # -- Teams card ----------------------------------------------------------------
    def _teams_card(self) -> Card:
        self.teams = Card("Microsoft Teams")
        badge_row = QHBoxLayout()
        self.auth_badge = Badge(tr("not_logged_in"), Badge.ERR)
        self.sync_badge = Badge(tr("last_sync") + ": —", Badge.MUTED)
        badge_row.addWidget(self.auth_badge)
        badge_row.addWidget(self.sync_badge)
        badge_row.addStretch(1)
        self.teams.addLayout(badge_row)

        self.lbl_user = QLabel("—")
        self.lbl_user.setStyleSheet("font-size:16px; font-weight:600;")
        self.teams.add(self.lbl_user)
        self.lbl_error = QLabel("")
        self.lbl_error.setObjectName("muted")
        self.lbl_error.setWordWrap(True)
        self.teams.add(self.lbl_error)

        row = QHBoxLayout()
        self.btn_login = QPushButton(tr("login"))
        self.btn_login.setObjectName("primary")
        self.btn_logout = QPushButton(tr("logout"))
        row.addWidget(self.btn_login)
        row.addWidget(self.btn_logout)
        row.addStretch(1)
        self.teams.addLayout(row)

        form = QFormLayout()
        self.client_id_edit = QLineEdit()
        form.addRow(tr("client_id"), self.client_id_edit)
        self.tenant_edit = QLineEdit("common")
        form.addRow("Tenant", self.tenant_edit)
        self.interval_spin = QSpinBox()
        self.interval_spin.setRange(20, 3600)
        self.interval_spin.setSuffix(" s")
        form.addRow(tr("interval"), self.interval_spin)
        self.teams.lay.addLayout(form)
        hint = QLabel(tr("ms_app_hint"))
        hint.setObjectName("muted")
        hint.setWordWrap(True)
        self.teams.add(hint)

        self.btn_save_ms = QPushButton(tr("save"))
        self.teams.add(self.btn_save_ms)
        self.btn_login.clicked.connect(self._login)
        self.btn_logout.clicked.connect(self._logout)
        self.btn_save_ms.clicked.connect(self._save_ms)
        return self.teams

    # -- Outlook card ---------------------------------------------------------------
    def _outlook_card(self) -> Card:
        self.outlook = Card("Microsoft 365 Kalender")
        form = QFormLayout()
        self.cal_toggle = ToggleRow(tr("calendar_enable"))
        form.addRow(self.cal_toggle)
        self.buffer_before = QSpinBox()
        self.buffer_before.setRange(0, 60)
        self.buffer_before.setSuffix(" min")
        form.addRow(tr("buffer_before"), self.buffer_before)
        self.buffer_after = QSpinBox()
        self.buffer_after.setRange(0, 60)
        self.buffer_after.setSuffix(" min")
        form.addRow(tr("buffer_after"), self.buffer_after)
        self.conflict = QComboBox()
        for ident, label in CONFLICTS:
            self.conflict.addItem(label, ident)
        form.addRow(tr("conflict"), self.conflict)
        self.scope = QSpinBox()
        self.scope.setRange(60, 10080)
        self.scope.setValue(1440)
        self.scope.setSuffix(" min")
        form.addRow("Betrachtungszeitraum", self.scope)
        self.outlook.lay.addLayout(form)
        self.btn_save_cal = QPushButton(tr("save"))
        self.outlook.add(self.btn_save_cal)
        self.btn_save_cal.clicked.connect(self._save_calendar)
        self.lbl_cal_error = QLabel("")
        self.lbl_cal_error.setObjectName("muted")
        self.lbl_cal_error.setWordWrap(True)
        self.outlook.add(self.lbl_cal_error)
        return self.outlook

    # -- webhooks -------------------------------------------------------------------
    def _webhook_card(self) -> Card:
        self.webhook = Card(tr("webhooks"))
        row = QHBoxLayout()
        self.btn_new_hook = QPushButton(tr("new_webhook"))
        self.btn_del_hook = QPushButton(tr("delete"))
        row.addWidget(self.btn_new_hook)
        row.addWidget(self.btn_del_hook)
        row.addStretch(1)
        self.webhook.addLayout(row)
        self.hook_table = QTableWidget(0, 5)
        self.hook_table.setHorizontalHeaderLabels(
            [tr("name"), "Token", tr("color"), tr("effect"), "Dauer (s)"])
        self.hook_table.verticalHeader().setVisible(False)
        self.hook_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.hook_table.horizontalHeader().setStretchLastSection(True)
        self.webhook.add(self.hook_table)
        self.lbl_hook_url = QLabel("")
        self.lbl_hook_url.setObjectName("muted")
        self.lbl_hook_url.setWordWrap(True)
        self.webhook.add(self.lbl_hook_url)
        self.btn_new_hook.clicked.connect(self._new_hook)
        self.btn_del_hook.clicked.connect(self._del_hook)
        return self.webhook

    def _api_card(self) -> Card:
        card = Card(tr("api_info"))
        form = QFormLayout()
        self._host_edit = QLineEdit("127.0.0.1")
        self._port_spin = QSpinBox()
        self._port_spin.setRange(1024, 65535)
        self._port_spin.setValue(17800)
        form.addRow("Bind-Adresse", self._host_edit)
        form.addRow("Port", self._port_spin)
        self.lbl_api = QLabel("")
        self.lbl_api.setObjectName("muted")
        self.lbl_api.setWordWrap(True)
        card.add(self.lbl_api)
        card.lay.addLayout(form)
        self.api_toggle = ToggleRow("Netzwerkzugriff über LAN (Token erforderlich)")
        card.add(self.api_toggle)
        self.btn_save_api = QPushButton(tr("save"))
        card.add(self.btn_save_api)
        self.btn_save_api.clicked.connect(self._save_api)
        return card

    # -- data -----------------------------------------------------------------------
    def refresh(self) -> None:
        api_client.run_async(lambda: api_client.call("GET", "/api/auth/status"), self._apply_auth)
        api_client.run_async(lambda: api_client.call("GET", "/api/settings"), self._apply_settings)
        api_client.run_async(lambda: api_client.call("GET", "/api/webhooks"), self._apply_hooks)
        api_client.run_async(lambda: api_client.call("GET", "/api/calendar/upcoming"),
                             self._apply_calendar)
        api_client.run_async(lambda: api_client.call("GET", "/api/presence"), self._apply_presence)

    def _apply_auth(self, data: dict) -> None:
        if data.get("_unreachable"):
            self.lbl_user.setText("Kern offline")
            return
        self.lbl_user.setText(data.get("user") or "—")
        if data.get("logged_in"):
            self.auth_badge.setText("verbunden")
            self.auth_badge.set_kind(Badge.OK)
            self.btn_login.setEnabled(False)
            self.btn_logout.setEnabled(True)
        else:
            self.auth_badge.setText(tr("not_logged_in"))
            self.auth_badge.set_kind(Badge.ERR)
            self.btn_login.setEnabled(True)
            self.btn_logout.setEnabled(False)
        if not data.get("configured"):
            self.lbl_error.setText("⚠ " + tr("ms_app_hint"))
        else:
            self.lbl_error.setText("")

    def _apply_presence(self, data: dict) -> None:
        if data.get("_unreachable"):
            return
        if data.get("last_error"):
            self.lbl_error.setText("⚠ " + str(data.get("last_error"))
                                   + ("\nHinweis: " + data["hint"] if data.get("hint") else ""))
        else:
            p = data.get("presence")
            if p:
                self.lbl_error.setText(
                    f"Aktuell: {p.get('availability')} / {p.get('activity')} ({p.get('ts')})")
    def _apply_settings(self, data: dict) -> None:
        if data.get("_unreachable"):
            return
        if not self.client_id_edit.hasFocus():
            self.client_id_edit.setText(str(data.get("ms.client_id") or ""))
        if not self.tenant_edit.hasFocus():
            self.tenant_edit.setText(str(data.get("ms.tenant") or "common"))
        self.interval_spin.setValue(int(data.get("sync.interval_seconds", 60) or 60))
        self.cal_toggle.setChecked(str(data.get("calendar.enabled", "false")).lower() == "true")
        self.buffer_before.setValue(int(data.get("calendar.buffer_before", 5) or 5))
        self.buffer_after.setValue(int(data.get("calendar.buffer_after", 0) or 0))
        idx = self.conflict.findData(str(data.get("presence.conflict_policy", "teams_after_meeting")))
        self.conflict.setCurrentIndex(max(0, idx))
        self.scope.setValue(int(data.get("calendar.scope_minutes", 1440) or 1440))
        host = data.get("api.host", "127.0.0.1")
        port = data.get("api.port", "17800")
        self._host_edit.setText(host)
        self._port_spin.setValue(int(port or 17800))
        self.api_toggle.setChecked(str(data.get("api.expose_lan", "false")).lower() == "true")
        self.lbl_api.setText(
            f"REST-API: http://{host}:{port}\n"
            "Endpoints: GET/POST /api/status · GET /api/devices · POST /api/device/color · "
            "POST /api/device/off · POST /api/profile/activate · GET /api/events (SSE)\n"
            "Standardmäßig nur localhost. Bei Netzwerkfreigabe ist ein Bearer-Token "
            "verpflichtend (api.expose_lan).")

    def _apply_hooks(self, data: dict) -> None:
        if data.get("_unreachable"):
            return
        hooks = data.get("webhooks", [])
        self.lbl_hook_url.setText("Trigger: POST " + str(data.get("url", "")))
        self.hook_table.setRowCount(len(hooks))
        for i, h in enumerate(hooks):
            self.hook_table.setItem(i, 0, QTableWidgetItem(str(h.get("name", ""))))
            self.hook_table.setItem(i, 1, QTableWidgetItem(str(h.get("token", ""))))
            self.hook_table.setItem(i, 2, QTableWidgetItem(str(h.get("color", ""))))
            self.hook_table.setItem(i, 3, QTableWidgetItem(str(h.get("effect", ""))))
            self.hook_table.setItem(i, 4, QTableWidgetItem(str(h.get("duration", ""))))

    def _apply_calendar(self, data: dict) -> None:
        if data.get("_unreachable"):
            return
        if data.get("last_error"):
            self.lbl_cal_error.setText("⚠ " + str(data.get("last_error")))

    # -- actions ----------------------------------------------------------------------
    def _open_setup(self) -> None:
        dlg = TeamsSetupDialog(self)
        dlg.client_id_edit.setText(self.client_id_edit.text())
        dlg.tenant_edit.setText(self.tenant_edit.text())
        if dlg.exec():
            self.client_id_edit.setText(dlg.client_id_edit.text())
            self.refresh()

    def _login(self) -> None:
        """One-click-Flow wie in der Windows-App: Mit hinterlegter Client-ID
        öffnet sich direkt der Microsoft-Browser-Dialog; die App prüft danach
        selbst die Berechtigungen und aktiviert die Synchronisierung.
        Ohne Client-ID öffnet sich einmalig der Einrichtungsassistent."""
        st = api_client.call("GET", "/api/auth/status", timeout=4)
        if not st.get("configured"):
            self._open_setup()
            return
        self.btn_login.setEnabled(False)
        self.lbl_user.setText("Browser-Anmeldung läuft …")
        api_client.run_async(lambda: api_client.call("POST", "/api/auth/login", timeout=180),
                             self._login_done)

    def _login_done(self, data: dict) -> None:
        self.btn_login.setEnabled(True)
        if data.get("ok"):
            QMessageBox.information(self, "Microsoft Teams",
                                    f"Angemeldet als {data.get('account', {}).get('user', '')}")
        else:
            msg = data.get("message") or str(data)
            hint = f"\n\nHinweis: {data.get('hint')}" if data.get("hint") else ""
            QMessageBox.warning(self, "Microsoft Teams", msg + hint)
        self.refresh()

    def _logout(self) -> None:
        api_client.run_async(lambda: api_client.call("POST", "/api/auth/logout"),
                             lambda d: self.refresh())

    def _save_ms(self) -> None:
        payload = {"ms.client_id": self.client_id_edit.text().strip(),
                   "ms.tenant": self.tenant_edit.text().strip() or "common",
                   "sync.interval_seconds": str(self.interval_spin.value())}
        api_client.run_async(lambda p=payload: api_client.call("PUT", "/api/settings", p),
                             lambda d: self.refresh())

    def _save_calendar(self) -> None:
        payload = {"calendar.enabled": str(self.cal_toggle.isChecked()).lower(),
                   "calendar.buffer_before": str(self.buffer_before.value()),
                   "calendar.buffer_after": str(self.buffer_after.value()),
                   "calendar.scope_minutes": str(self.scope.value()),
                   "presence.conflict_policy": self.conflict.currentData()}
        api_client.run_async(lambda p=payload: api_client.call("PUT", "/api/settings", p),
                             lambda d: self.refresh())

    def _save_api(self) -> None:
        payload = {"api.host": self._host_edit.text().strip() or "127.0.0.1",
                   "api.port": str(self._port_spin.value()),
                   "api.expose_lan": str(self.api_toggle.isChecked()).lower()}
        api_client.run_async(lambda p=payload: api_client.call("PUT", "/api/settings", p),
                             lambda d: QMessageBox.information(
                                 self, tr("api_info"), "Gespeichert. Der Kern nutzt die "
                                 "neue Adresse beim nächsten Start bzw. Neustart."))

    def _new_hook(self) -> None:
        name, ok = QInputDialog.getText(self, tr("new_webhook"), tr("name"))
        if not ok or not name.strip():
            return
        payload = {"name": name.strip(), "color": "#FF0044", "effect": "strobe:4", "duration": 60}
        api_client.run_async(lambda p=payload: api_client.call("POST", "/api/webhooks", p),
                             lambda d: self.refresh())

    def _del_hook(self) -> None:
        row = self.hook_table.currentRow()
        if row < 0:
            return
        hooks = [h for h in self._get_hooks()]
        if row >= len(hooks):
            return
        hid = hooks[row]["id"]

        def do():
            return api_client.call("DELETE", f"/api/webhooks/{hid}")

        api_client.run_async(do, lambda d: self.refresh())

    def _get_hooks(self):
        data = api_client.call("GET", "/api/webhooks")
        return data.get("webhooks", [])


class ToggleRow(QWidget):
    def __init__(self, label: str) -> None:
        super().__init__()
        from PySide6.QtWidgets import QCheckBox
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.checkbox = QCheckBox(label)
        lay.addWidget(self.checkbox)
        lay.addStretch(1)

    def isChecked(self) -> bool:  # noqa: N802
        return self.checkbox.isChecked()

    def setChecked(self, v: bool) -> None:  # noqa: N802
        self.checkbox.setChecked(bool(v))