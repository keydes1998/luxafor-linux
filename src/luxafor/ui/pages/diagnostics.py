"""Diagnostics page: system checks, log tail, redacted export."""
from __future__ import annotations

import time

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QMessageBox, QPushButton, QScrollArea, QVBoxLayout,
    QWidget, QFileDialog, QFrame, QTabWidget,
)

from luxafor.ui import api_client
from luxafor.ui.i18n import tr
from luxafor.ui.widgets import Badge, Card, LogView


class DiagnosticsPage(QWidget):
    def __init__(self) -> None:
        super().__init__()
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(16)

        title = QLabel(tr("Diagnostics"))
        title.setObjectName("h1")
        sub = QLabel(tr("diagnostics_desc"))
        sub.setObjectName("muted")
        root.addWidget(title)
        root.addWidget(sub)

        row = QHBoxLayout()
        self.btn_refresh = QPushButton("Neu prüfen")
        self.btn_refresh.setObjectName("primary")
        self.btn_export = QPushButton(tr("export_logs"))
        row.addWidget(self.btn_refresh)
        row.addWidget(self.btn_export)
        row.addStretch(1)
        root.addLayout(row)

        tabs = QTabWidget()
        root.addWidget(tabs, 1)

        checks_tab = QWidget()
        cl = QVBoxLayout(checks_tab)
        self.checks_host = QVBoxLayout()
        self.checks_host.setContentsMargins(0, 0, 0, 0)
        cl.addLayout(self.checks_host)
        cl.addStretch(1)
        tabs.addTab(checks_tab, "Prüfungen")

        log_tab = QWidget()
        ll = QVBoxLayout(log_tab)
        self.log = LogView()
        ll.addWidget(self.log)
        tabs.addTab(log_tab, "Protokoll")

        self.btn_refresh.clicked.connect(self.refresh)
        self.btn_export.clicked.connect(self._export)

        self.timer = QTimer(self)
        self.timer.setInterval(10000)
        self.timer.timeout.connect(self.refresh)
        self.timer.start()
        self.refresh()

    def refresh(self) -> None:
        api_client.run_async(lambda: api_client.call("GET", "/api/diagnostics"), self._apply_checks)
        api_client.run_async(lambda: api_client.call("GET", "/api/logs?lines=200"), self._apply_logs)

    def _apply_checks(self, data: dict) -> None:
        if data.get("_unreachable"):
            item = Card("Kern nicht erreichbar")
            lbl = QLabel("Der Hintergrunddienst läuft nicht. "
                         "Start: systemctl --user start luxafor-core oder lx-core.")
            lbl.setWordWrap(True)
            item.add(lbl)
            self._set_checks([item])
            return
        cards = []
        for c in data.get("checks", []):
            card = Card()
            row = QHBoxLayout()
            state = c.get("ok")
            badge_kind = {True: Badge.OK, False: Badge.ERR}.get(state, Badge.MUTED)
            badge_text = {True: "OK", False: "FEHLER"}.get(state, "—")
            card.row(QLabel(f"<b>{c.get('check')}</b>"), Badge(badge_text, badge_kind))
            lbl = QLabel(str(c.get("message", "")))
            lbl.setWordWrap(True)
            card.add(lbl)
            if c.get("hint") and state is False:
                hint = QLabel("💡 " + str(c.get("hint")))
                hint.setObjectName("muted")
                hint.setWordWrap(True)
                card.add(hint)
            cards.append(card)
        self._set_checks(cards)

        # device summary card
        devices = data.get("devices", [])
        if devices:
            card = Card()
            card.row(QLabel("<b>Geräte</b>"),
                     QLabel(", ".join(f"{d.get('id')} ({d.get('model')})" for d in devices)))
            cards.append(card)

    def _set_checks(self, cards: list) -> None:
        while self.checks_host.count():
            item = self.checks_host.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        host = QWidget()
        v = QVBoxLayout(host)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(10)
        for c in cards:
            v.addWidget(c)
        v.addStretch(1)
        sc = QScrollArea()
        sc.setWidgetResizable(True)
        sc.setFrameShape(QScrollArea.NoFrame)
        sc.setWidget(host)
        wrapper = QWidget()
        wl = QVBoxLayout(wrapper)
        wl.setContentsMargins(0, 0, 0, 0)
        wl.addWidget(sc)
        self.checks_host.addWidget(wrapper)

    def _apply_logs(self, data: dict) -> None:
        if data.get("_unreachable"):
            self.log.append_lines("Kern nicht erreichbar.")
            return
        self.log.append_lines(data.get("lines", []))

    def _export(self) -> None:
        data = api_client.call("GET", "/api/logs/export")
        if data.get("error"):
            QMessageBox.warning(self, tr("export_logs"), str(data["error"]))
            return
        default = f"luxafor-diagnose-{time.strftime('%Y%m%d-%H%M%S')}.json"
        path, _ = QFileDialog.getSaveFileName(self, tr("export_logs"), default,
                                              "JSON (*.json);;Alle Dateien (*)")
        if not path:
            return
        try:
            import json
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2, ensure_ascii=False)
            QMessageBox.information(self, tr("export_logs"), "Export erfolgreich:\n" + path)
        except OSError as exc:
            QMessageBox.warning(self, tr("export_logs"), f"Export fehlgeschlagen: {exc}")