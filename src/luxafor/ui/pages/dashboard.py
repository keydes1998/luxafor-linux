"""Dashboard page: live status, quick controls and overview cards."""
from __future__ import annotations

import time

from PySide6.QtCore import QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QGridLayout, QHBoxLayout, QLabel, QScrollArea, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget, QPushButton,
)

from luxafor.ui import api_client
from luxafor.ui.i18n import tr
from luxafor.ui.widgets import Badge, Card, ColorPill


def fmt_ts(ts) -> str:
    if not ts:
        return tr("never")
    try:
        return time.strftime("%H:%M:%S", time.localtime(float(ts)))
    except (TypeError, ValueError):
        return str(ts)


class DashboardPage(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self._paused = False
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(16)

        title = QLabel(tr("Dashboard"))
        title.setObjectName("h1")
        root.addWidget(title)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        inner = QWidget()
        grid = QGridLayout(inner)
        grid.setSpacing(14)
        grid.setColumnStretch(0, 3)
        grid.setColumnStretch(1, 2)
        scroll.setWidget(inner)
        root.addWidget(scroll)

        # --- status card ------------------------------------------------------
        self.status_card = Card(tr("current_status"))
        pill_lay = QHBoxLayout()
        pill_lay.setSpacing(14)
        self.pill = ColorPill(76)
        pill_lay.addWidget(self.pill)
        col = QVBoxLayout()
        self.lbl_effect = QLabel("—")
        self.lbl_effect.setStyleSheet("font-size:20px; font-weight:600;")
        self.lbl_origin = QLabel(tr("active_source") + ": —")
        self.lbl_origin.setObjectName("muted")
        badge_row = QHBoxLayout()
        self.badge_manual = Badge(tr("manual_active"), Badge.WARN)
        self.badge_paused = Badge(tr("pause_sync"), Badge.WARN)
        badge_row.addWidget(self.badge_manual)
        badge_row.addWidget(self.badge_paused)
        badge_row.addStretch(1)
        col.addWidget(self.lbl_effect)
        col.addWidget(self.lbl_origin)
        col.addLayout(badge_row)
        col.addStretch(1)
        pill_lay.addLayout(col, 1)
        self.status_card.addLayout(pill_lay)

        # --- quick controls -----------------------------------------------------
        quick = Card(tr("quick"))
        self.quick_row = QHBoxLayout()
        self.quick_grid = None
        self.quick_row.setSpacing(8)
        quick.lay.addLayout(self.quick_row)
        buttons_row = QHBoxLayout()
        self.btn_restore = QPushButton(tr("restore_auto"))
        self.btn_off = QPushButton(tr("led_off"))
        self.btn_pause = QPushButton(tr("pause_sync"))
        buttons_row.addWidget(self.btn_restore)
        buttons_row.addWidget(self.btn_off)
        buttons_row.addWidget(self.btn_pause)
        buttons_row.addStretch(1)
        quick.lay.addLayout(buttons_row)
        self.btn_restore.clicked.connect(self._restore)
        self.btn_off.clicked.connect(self._off)
        self.btn_pause.clicked.connect(self._toggle_pause)

        # --- right column -------------------------------------------------------
        self.teams_card = Card(tr("teams_status"))
        self.lbl_teams = QLabel(tr("not_logged_in"))
        self.lbl_teams.setStyleSheet("font-size:18px; font-weight:600;")
        self.lbl_teams_detail = QLabel("")
        self.lbl_teams_detail.setObjectName("muted")
        self.lbl_teams_detail.setWordWrap(True)
        self.teams_card.add(self.lbl_teams)
        self.teams_card.add(self.lbl_teams_detail)
        self.lbl_sync = QLabel(tr("last_sync") + ": " + tr("never"))
        self.lbl_sync.setObjectName("muted")
        self.teams_card.add(self.lbl_sync)

        self.cal_card = Card(tr("next_meeting"))
        self.lbl_calendar = QLabel("—")
        self.lbl_calendar.setStyleSheet("font-size:16px; font-weight:600;")
        self.lbl_calendar_detail = QLabel("")
        self.lbl_calendar_detail.setObjectName("muted")
        self.lbl_calendar_detail.setWordWrap(True)
        self.cal_card.add(self.lbl_calendar)
        self.cal_card.add(self.lbl_calendar_detail)

        self.dev_card = Card(tr("devices_connected"))
        self.dev_table = QTableWidget(0, 3)
        self.dev_table.setHorizontalHeaderLabels(["ID", "Modell", tr("color")])
        self.dev_table.verticalHeader().setVisible(False)
        self.dev_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.dev_table.horizontalHeader().setStretchLastSection(True)
        self.dev_table.setMinimumHeight(120)
        self.dev_table.setMaximumHeight(170)
        self.dev_table.setColumnWidth(0, 150)
        self.dev_table.setColumnWidth(1, 210)
        self.dev_card.add(self.dev_table)

        grid.addWidget(self.status_card, 0, 0)
        grid.addWidget(quick, 1, 0)
        grid.addWidget(self.dev_card, 2, 0)
        grid.addWidget(self.teams_card, 0, 1)
        grid.addWidget(self.cal_card, 1, 1)
        grid.addWidget(QWidget(), 2, 1)

        self.timer = QTimer(self)
        self.timer.setInterval(4000)
        self.timer.timeout.connect(self.refresh)
        self.timer.start()
        self._quick_built = False
        self.refresh()

    # -- actions ------------------------------------------------------------------
    def _restore(self) -> None:
        api_client.run_async(lambda: api_client.call("POST", "/api/status/restore", {}),
                             lambda _: self.refresh())

    def _off(self) -> None:
        api_client.run_async(lambda: api_client.call("POST", "/api/device/off", {}),
                             lambda _: self.refresh())

    def _toggle_pause(self) -> None:
        api_client.run_async(
            lambda: api_client.call("POST", "/api/sync/pause", {"paused": not self._paused}),
            lambda _: self.refresh())

    def _set_quick(self, data: dict) -> None:
        api_client.run_async(lambda: api_client.call("POST", "/api/status", data),
                             lambda _: self.refresh())

    # -- data refresh ---------------------------------------------------------------
    def refresh(self) -> None:
        api_client.run_async(lambda: api_client.call("GET", "/api/status"), self._apply_status)

    def _apply_status(self, data: dict) -> None:
        if data.get("_unreachable"):
            self.lbl_effect.setText("Kern offline")
            self.lbl_effect.setStyleSheet("font-size:20px; font-weight:600; color:#FF6D6D;")
            return
        self.lbl_effect.setStyleSheet("font-size:20px; font-weight:600;")
        cur = data.get("current", {})
        self.pill.set_color(cur.get("color", "#101218"), cur.get("effect", ""))
        self.lbl_effect.setText(f"{cur.get('color', '—')} · {cur.get('effect', 'solid')}")
        self.lbl_origin.setText(
            f"{tr('active_source')}: {cur.get('label', '—')} ({cur.get('origin', '—')})")
        self._paused = bool(data.get("paused"))
        self.badge_paused.setVisible(self._paused)
        self.badge_manual.setVisible(bool(data.get("manual_active")))
        self.btn_pause.setText(tr("resume_sync") if self._paused else tr("pause_sync"))

        if not self._quick_built:
            self._quick_built = True
            api_client.run_async(lambda: api_client.call("GET", "/api/statuses"),
                                 self._apply_statuses)

        pres = data.get("presence")
        if pres:
            self.lbl_teams.setText(str(pres.get("availability") or "—"))
            self.lbl_teams_detail.setText(
                f"Aktivität: {pres.get('activity') or '—'}   ·   {pres.get('ts', '')}")
        else:
            self.lbl_teams.setText(tr("not_logged_in"))
            self.lbl_teams_detail.setText(str(data.get("presence_last_error") or ""))
        sync_txt = f"{tr('last_sync')}: {fmt_ts(data.get('last_sync_ok'))}"
        if data.get("last_sync_error"):
            sync_txt += f"  ·  Fehler: {data.get('last_sync_error')}"
        self.lbl_sync.setText(sync_txt)

        nxt = data.get("calendar_next")
        self.lbl_calendar.setText(str(nxt or "—"))

        devices = data.get("devices") or []
        self.dev_table.setRowCount(len(devices))
        for i, d in enumerate(devices):
            self.dev_table.setItem(i, 0, QTableWidgetItem(str(d.get("id", ""))))
            self.dev_table.setItem(i, 1, QTableWidgetItem(str(d.get("model", ""))))
            item = QTableWidgetItem(str(d.get("color", "")))
            item.setForeground(QColor(str(d.get("color") or "#9AA3B2")))
            self.dev_table.setItem(i, 2, item)

    def _apply_statuses(self, data: dict) -> None:
        """2x4-Raster: passt auch in schmale Fenster ohne Überlauf."""
        # bestehendes Grid leeren
        if self.quick_grid is not None:
            while self.quick_grid.count():
                gi = self.quick_grid.takeAt(0)
                if gi.widget():
                    gi.widget().deleteLater()
            self.quick_row.removeItem(self.quick_grid)
            self.quick_grid.deleteLater()
        grid = QGridLayout()
        grid.setSpacing(8)
        statuses = (data.get("statuses") or [])[:8]
        for i, st in enumerate(statuses):
            name = str(st.get("name", "?"))
            color = str(st.get("color", "#FF0000"))
            btn = QPushButton(name)
            btn.setStyleSheet(
                f"background:{color}; border:1px solid #2C313D; border-radius:10px;"
                "padding:8px 12px; font-weight:600; color:#FFFFFF;")
            btn.clicked.connect(
                lambda _=False, st=st: self._set_quick({
                    "status": st.get("name"),
                    "color": st.get("color"),
                    "effect": st.get("effect") or "solid",
                    "duration": int(st.get("duration") or 0),
                }))
            grid.addWidget(btn, i // 4, i % 4)
        self.quick_row.addLayout(grid)
        self.quick_grid = grid