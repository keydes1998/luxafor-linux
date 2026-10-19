"""Profiles page: bundled color mappings and rulesets."""
from __future__ import annotations

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QHBoxLayout, QInputDialog, QLabel, QMessageBox, QPushButton,
    QScrollArea, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from luxafor.ui import api_client
from luxafor.ui.i18n import tr
from luxafor.ui.widgets import Badge, Card

PRESET_PROFILES = ["Büro", "Homeoffice", "Fokus", "Meeting", "Feierabend"]


class ProfilesPage(QWidget):
    def __init__(self) -> None:
        super().__init__()
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(16)

        title = QLabel(tr("Profiles"))
        title.setObjectName("h1")
        root.addWidget(title)

        self.hint = Card()
        lbl = QLabel(tr("profiles_hint") + "\n" +
                     "Ein Profil kann eine Standardfarbe vorgeben (data.default_color) und wird "
                     "im Menü sowie in der CLI aktiviert: POST /api/profile/activate.")
        lbl.setWordWrap(True)
        self.hint.add(lbl)
        add_row = QHBoxLayout()
        self.btn_new = QPushButton(tr("new_profile"))
        self.btn_activate = QPushButton(tr("activate"))
        self.btn_delete = QPushButton(tr("delete"))
        add_row.addWidget(self.btn_new)
        add_row.addWidget(self.btn_activate)
        add_row.addWidget(self.btn_delete)
        add_row.addStretch(1)
        self.hint.lay.addLayout(add_row)
        root.addWidget(self.hint)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(
            ["ID", tr("name"), tr("active"), "Konfiguration"])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.horizontalHeader().setStretchLastSection(True)
        root.addWidget(self.table, 1)

        self.btn_new.clicked.connect(self._new_profile)
        self.btn_activate.clicked.connect(self._activate)
        self.btn_delete.clicked.connect(self._delete)

        self.timer = QTimer(self)
        self.timer.setInterval(6000)
        self.timer.timeout.connect(self.refresh)
        self.timer.start()
        self.refresh()

    def refresh(self) -> None:
        api_client.run_async(lambda: api_client.call("GET", "/api/profiles"), self._apply)

    def _apply(self, data: dict) -> None:
        if data.get("_unreachable"):
            return
        profiles = data.get("profiles", [])
        self._profiles = profiles
        self.table.setRowCount(len(profiles))
        import json
        for i, p in enumerate(profiles):
            self.table.setItem(i, 0, QTableWidgetItem(str(p.get("id"))))
            self.table.setItem(i, 1, QTableWidgetItem(str(p.get("name"))))
            active_item = QTableWidgetItem("aktuell" if p.get("active") else "—")
            self.table.setItem(i, 2, active_item)
            self.table.setItem(i, 3, QTableWidgetItem(
                json.dumps(p.get("data", {}), ensure_ascii=False)[:400]))

    def _new_profile(self) -> None:
        name, ok = QInputDialog.getItem(
            self, tr("new_profile"), tr("name"),
            PRESET_PROFILES, 0, True)
        if not ok or not name.strip():
            return
        api_client.run_async(
            lambda n=name.strip(): api_client.call("POST", "/api/profiles",
                                                   {"name": n, "data": {"default_color": "#00AA00"}}),
            lambda d: self.refresh())

    def _selected(self) -> dict | None:
        row = self.table.currentRow()
        if row < 0 or not hasattr(self, "_profiles"):
            return None
        return self._profiles[row]

    def _activate(self) -> None:
        prof = self._selected()
        if not prof:
            return
        api_client.run_async(
            lambda p=prof: api_client.call("POST", "/api/profile/activate", {"id": p["id"]}),
            lambda d: self.refresh())

    def _delete(self) -> None:
        prof = self._selected()
        if not prof:
            return
        if QMessageBox.question(self, tr("delete"),
                                f"Profil '{prof.get('name')}' löschen?") != QMessageBox.Yes:
            return
        api_client.run_async(lambda p=prof: api_client.call("DELETE", f"/api/profiles/{p['id']}"),
                             lambda d: self.refresh())