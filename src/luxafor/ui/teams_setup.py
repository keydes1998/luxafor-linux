"""Microsoft-365-Setup-Assistent (Einmal-Anmeldung): 4 Schritte als Dialog.

Schritte laut Spezifikation:
  1) Microsoft-365-Konto verbinden (App-Registrierung: Client-ID + Redirect)
  2) Microsoft-Anmeldung durchführen (Browser, PKCE, Loopback)
  3) Berechtigungen prüfen (Presence/Calendar konkret testen)
  4) Verbindung testen + Synchronisierung aktivieren

Die Anmeldung selbst ist einmalig: MSAL speichert Refresh-Token im Secret
Service (KDE Wallet/GNOME Keyring) und erneuert sie automatisch. Die Graph-API
ist die dokumentierte Quelle für den Teams-Status — Alternativen (lokales
Auslesen des Windows-Teams-Clients) existieren unter Linux nicht.
"""
from __future__ import annotations

import webbrowser

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QDialog, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
    QPushButton, QStackedWidget, QVBoxLayout, QWidget, QFormLayout,
)

from luxafor.ui import api_client
from luxafor.ui.i18n import tr
from luxafor.ui.widgets import Badge


PORTAL_APP_REGISTRATIONS = "https://portal.azure.com/#blade/Microsoft_AAD_RegisteredApps/ApplicationsListBlade"
PORTAL_PERMISSIONS_HELP = "https://learn.microsoft.com/graph/auth-v2-user"


class TeamsSetupDialog(QDialog):
    def __init__(self, parent) -> None:
        super().__init__(parent)
        self.setWindowTitle("Microsoft Teams einrichten")
        self.setMinimumWidth(560)
        self.setModal(True)

        root = QVBoxLayout(self)
        self.stack = QStackedWidget()
        root.addWidget(self.stack)
        self.stack.addWidget(self._page1_cid())
        self.stack.addWidget(self._page2_login())
        self.stack.addWidget(self._page3_verify())
        self.stack.addWidget(self._page4_done())

    # ---------------------------------------------------------------- pages
    def _page1_cid(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        head = QLabel("<b>Schritt 1 — Microsoft-365-Konto verbinden</b>")
        lay.addWidget(head)
        lay.addWidget(QLabel(
            "Für die Teams-Status-Synchronisierung braucht die App eine Entra-ID-"
            "App-Registrierung (einmalig, ~5 Minuten, danach nie wieder):"))
        tips = QLabel(
            "1. <a href='" + PORTAL_APP_REGISTRATIONS + "'>App-Registrierungen öffnen</a> "
            "(Entra Admin Center)\n"
            "2. Neue Registrierung, Name z. B. „Luxafor Linux“, "
            "**Zielgruppe: Einmieter (Single Tenant) oder beliebig*\n"
            "3. Redirect-URI: Plattform „Mobilgerät und Desktop“, "
            "Wert <code>http://localhost</code>\n"
            "4. API-Berechtigungen (delegiert): <code>User.Read</code>, "
            "<code>Presence.Read</code>, <code>Calendars.Read</code>*\n"
            "*Calendars.Read nur für Outlook-Kalender; ggf. Administrator-Zustimmung.\n\n"
            "5. Client-ID (Anwendungs-ID) hier eintragen:"
        )
        tips.setTextFormat(Qt.RichText)
        tips.setTextInteractionFlags(Qt.TextBrowserInteraction)
        tips.linkActivated.connect(lambda url: webbrowser.open(url))
        lay.addWidget(tips)
        form = QFormLayout()
        self.client_id_edit = QLineEdit()
        self.tenant_edit = QLineEdit("common")
        form.addRow(tr("client_id"), self.client_id_edit)
        form.addRow("Tenant (oder common)", self.tenant_edit)
        lay.addLayout(form)

        row = QHBoxLayout()
        self.btn_save_id = QPushButton("Weiter →")
        self.btn_save_id.setObjectName("primary")
        row.addStretch(1)
        row.addWidget(self.btn_save_id)
        lay.addLayout(row)
        self.btn_save_id.clicked.connect(self._step1_save)
        return w

    def _page2_login(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.addWidget(QLabel("<b>Schritt 2 — Microsoft-Anmeldung</b>"))
        lay.addWidget(QLabel(
            "Es öffnet sich der Standardbrowser für die Microsoft-Anmeldung "
            "(OAuth 2.0 mit PKCE, Tokens landen im System-Keyring). "
            "Danach musst du dich NIE wieder manuell anmelden — die App erneuert "
            "die Tokens automatisch."))
        self.lbl_login_state = QLabel("")
        self.lbl_login_state.setObjectName("muted")
        lay.addWidget(self.lbl_login_state)
        row = QHBoxLayout()
        self.btn_login_go = QPushButton("Microsoft-Anmeldung öffnen")
        self.btn_login_go.setObjectName("primary")
        self.btn_back1 = QPushButton("Zurück")
        row.addWidget(self.btn_back1)
        row.addStretch(1)
        row.addWidget(self.btn_login_go)
        lay.addLayout(row)
        lay.addStretch(1)
        self.btn_login_go.clicked.connect(self._step2_login)
        self.btn_back1.clicked.connect(lambda: self.stack.setCurrentIndex(0))
        return w

    def _page3_verify(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.addWidget(QLabel("<b>Schritt 3 — Berechtigungen prüfen</b>"))
        lay.addWidget(QLabel("Die App testet konkret Presence und Kalender."))
        self.lbl_verify = QLabel("Prüfe …")
        self.lbl_verify.setWordWrap(True)
        lay.addWidget(self.lbl_verify)
        lay.addStretch(1)
        return w

    def _page4_done(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.addWidget(QLabel("<b>Schritt 4 — Fertig</b>"))
        self.chk_sync = QCheckBox("Teams-Synchronisierung aktivieren")
        self.chk_sync.setChecked(True)
        lay.addWidget(self.chk_sync)
        self.lbl_done = QLabel("")
        self.lbl_done.setObjectName("muted")
        lay.addWidget(self.lbl_done)
        lay.addStretch(1)
        row = QHBoxLayout()
        self.btn_finish = QPushButton("Abschließen")
        self.btn_finish.setObjectName("primary")
        row.addStretch(1)
        row.addWidget(self.btn_finish)
        lay.addLayout(row)
        self.btn_finish.clicked.connect(self._finish)
        return w

    # ------------------------------------------------------------- actions
    def _step1_save(self) -> None:
        cid = self.client_id_edit.text().strip()
        if not cid:
            QMessageBox.information(self, "Client-ID",
                                    "Bitte die Application-ID (Client-ID) eintragen.")
            return
        payload = {"ms.client_id": cid, "ms.tenant": self.tenant_edit.text().strip() or "common",
                   "sync.enabled": "true"}
        api_client.run_async(lambda p=payload: api_client.call("PUT", "/api/settings", p),
                             self._step1_done)

    def _step1_done(self, _data) -> None:
        self.stack.setCurrentIndex(1)

    def _step2_login(self) -> None:
        self.lbl_login_state.setText("Warte auf Microsoft-Anmeldung im Browser …")
        api_client.run_async(
            lambda: api_client.call("POST", "/api/auth/login", timeout=200),
            self._step2_done)

    def _step2_done(self, data: dict) -> None:
        if data.get("ok"):
            self.lbl_login_state.setText("Anmeldung erfolgreich ✓")
            self.stack.setCurrentIndex(2)
            api_client.run_async(lambda: api_client.call("POST", "/api/auth/verify"),
                                 self._verify_done)
        else:
            msg = str(data.get("message") or data)
            hint = f"\n\nHinweis: {data.get('hint')}" if data.get("hint") else ""
            self.lbl_login_state.setText("Anmeldung fehlgeschlagen. Nochmal probieren.")
            QMessageBox.warning(self, "Microsoft-Anmeldung", msg + hint)

    def _verify_done(self, data: dict) -> None:
        from PySide6.QtCore import QTimer
        lines = []
        user = str(data.get("user") or "?")
        lines.append(f"Angemeldet als: {user}")
        avail = data.get("scopes_available") or {}
        if avail:
            lines.append("Berechtigungen:")
            for scope, ok in avail.items():
                lines.append(f"  {'✓' if ok else '✗'} {scope}")
            missing = [s for s, ok in avail.items() if not ok]
            if missing and "Presence.Read" in avail and not avail.get("Presence.Read"):
                lines.append("⚠ Presence.Read fehlt → Admin-Zustimmung nötig im Entra-Konfiguration "
                             "→ API-Berechtigungen (delegiert), danach erneut Anmeldung.")
            elif missing:
                lines.append(f"({', '.join(missing)} fehlt – Sync läuft trotzdem mit den übrigen)")
        pres = data.get("presence", {})
        cal = data.get("calendar", {})
        if pres.get("ok"):
            p = pres.get("value", {})
            lines.append(f"✓ Presence.Read OK — aktueller Status: {p.get('availability')} / {p.get('activity')}")
        else:
            lines.append(f"✗ Presence FEHLGESCHLAGEN: {pres.get('error')}")
            if pres.get("hint"):
                lines.append(f"  → {pres['hint']}")
        if cal.get("ok"):
            lines.append(f"✓ Calendars.Read OK — {cal.get('count', 0)} Termine gefunden")
        else:
            lines.append(f"(Kalender: {cal.get('error') or 'nicht getestet'})")
        self.lbl_verify.setText("\n".join(lines))
        if bool(data.get("ok")):
            # vollautomischer Abschluss wie in der Windows-App:
            # Sync aktivieren und Dialog schließen — kein weiterer Klick
            api_client.run_async(
                lambda: api_client.call("PUT", "/api/settings", {"sync.enabled": "true",
                                                                  "calendar.enabled": "true"}),
                lambda d: self._auto_finish())
        else:
            self.stack.setCurrentIndex(0)  # zurück zur Client-ID/Erklärung
            QMessageBox.warning(self, "Berechtigungen",
                                "Die Microsoft-Organisation hat die Berechtigungen "
                                "nicht (oder noch nicht) freigegeben:\n"
                                + "\n".join(lines[1:]))
            QTimer.singleShot(0, None)

    def _auto_finish(self) -> None:
        self.lbl_done.setText("Synchronisierung aktiviert ✓ — Die Anmeldung gilt "
                              "dauerhaft (Refresh-Tokens im System-Keyring).")
        from PySide6.QtCore import QTimer
        QTimer.singleShot(1500, self.accept)

    def _finish(self) -> None:
        if self.chk_sync.isChecked():
            api_client.run_async(
                lambda: api_client.call("PUT", "/api/settings", {"sync.enabled": "true"}),
                lambda d: None)
        self.accept()