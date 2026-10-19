"""Automations page: rules CRUD and rule activity log."""
from __future__ import annotations

import json

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QCheckBox, QDialog, QDoubleSpinBox, QFormLayout, QHBoxLayout, QInputDialog,
    QLabel, QLineEdit, QMessageBox, QPushButton, QScrollArea, QTabWidget,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget, QComboBox,
)

from luxafor.ui import api_client
from luxafor.ui.i18n import tr
from luxafor.ui.widgets import ColorButton, EffectPicker, LogView, ParamForm

RULE_TYPES = [
    ("presence", "Teams-Präsenz"),
    ("calendar", "Outlook-Kalender"),
    ("schedule", "Zeitplan"),
    ("idle", "Benutzer abwesend"),
    ("lock", "Bildschirmsperre"),
    ("webhook", "Webhook"),
]


class AutomationsPage(QWidget):
    def __init__(self) -> None:
        super().__init__()
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(16)

        title = QLabel(tr("Automations"))
        title.setObjectName("h1")
        root.addWidget(title)

        tabs = QTabWidget()
        root.addWidget(tabs, 1)

        # --- rules tab -------------------------------------------------------------
        rules_tab = QWidget()
        rl = QVBoxLayout(rules_tab)
        top = QHBoxLayout()
        self.btn_new = QPushButton(tr("new_rule"))
        self.btn_new.setObjectName("primary")
        self.btn_edit = QPushButton(tr("edit"))
        self.btn_delete = QPushButton(tr("delete"))
        top.addWidget(self.btn_new)
        top.addWidget(self.btn_edit)
        top.addWidget(self.btn_delete)
        top.addStretch(1)
        rl.addLayout(top)
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            ["ID", tr("name"), tr("type"), tr("color"), tr("effect"), tr("priority")])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.horizontalHeader().setStretchLastSection(True)
        rl.addWidget(self.table, 1)
        hint = QLabel("Prioritäten: 95 Kritisch · 90 Manuell · 80 Anruf/Präsentation · "
                      "70 Besprechung · 60 Fokus · 40 Präsenz · 30 Abwesenheit · 20 Zeitplan · 10 Standard")
        hint.setObjectName("muted")
        rl.addWidget(hint)

        # --- activity tab ------------------------------------------------------------
        act_tab = QWidget()
        al = QVBoxLayout(act_tab)
        self.log = LogView()
        al.addWidget(self.log)
        tabs.addTab(rules_tab, tr("rules"))
        tabs.addTab(act_tab, tr("activity"))

        self.btn_new.clicked.connect(self._new_rule)
        self.btn_edit.clicked.connect(self._edit_rule)
        self.btn_delete.clicked.connect(self._delete_rule)

        self.timer = QTimer(self)
        self.timer.setInterval(5000)
        self.timer.timeout.connect(self.refresh)
        self.timer.start()
        self.refresh()

    def refresh(self) -> None:
        api_client.run_async(lambda: api_client.call("GET", "/api/rules"), self._apply_rules)
        api_client.run_async(lambda: api_client.call("GET", "/api/activity"), self._apply_activity)

    def _apply_rules(self, data: dict) -> None:
        if data.get("_unreachable"):
            return
        rules = data.get("rules", [])
        self.table.setRowCount(len(rules))
        self._rules = rules
        type_names = dict(RULE_TYPES)
        for i, r in enumerate(rules):
            self.table.setItem(i, 0, QTableWidgetItem(str(r.get("id"))))
            self.table.setItem(i, 1, QTableWidgetItem(str(r.get("name"))))
            self.table.setItem(i, 2, QTableWidgetItem(type_names.get(r.get("type"), str(r.get("type")))))
            self.table.setItem(i, 3, QTableWidgetItem(str(r.get("color"))))
            self.table.setItem(i, 4, QTableWidgetItem(str(r.get("effect"))))
            prio_item = QTableWidgetItem(str(r.get("priority")))
            prio_item.setData(0, bool(r.get("enabled")))
            self.table.setItem(i, 5, prio_item)
        for i, r in enumerate(rules):
            if not r.get("enabled"):
                for j in range(6):
                    item = self.table.item(i, j)
                    if item:
                        import PySide6.QtGui as g
                        item.setForeground(g.QColor("#5A6272"))

    def _apply_activity(self, data: dict) -> None:
        if data.get("_unreachable"):
            return
        rows = []
        import time
        for a in reversed(data.get("activity", [])):
            ts = time.strftime("%H:%M:%S", time.localtime(a.get("ts", 0)))
            payload = a.get("payload", {})
            detail = payload.get("label") or payload.get("key") or ""
            rows.append(f"{ts}  {a.get('kind')}  {detail}")
        self.log.append_lines(rows)

    def _selected_rule(self) -> dict | None:
        row = self.table.currentRow()
        if row < 0 or not hasattr(self, "_rules"):
            return None
        return self._rules[row]

    def _new_rule(self) -> None:
        dlg = RuleDialog(self)
        if dlg.exec() and dlg.result_data():
            payload = dlg.result_data()
            api_client.run_async(lambda p=payload: api_client.call("POST", "/api/rules", p),
                                 lambda d: self.refresh())

    def _edit_rule(self) -> None:
        rule = self._selected_rule()
        if not rule:
            return
        dlg = RuleDialog(self, rule)
        if dlg.exec() and dlg.result_data():
            payload = dlg.result_data()
            rid = rule["id"]
            api_client.run_async(
                lambda p=payload, i=rid: api_client.call("PUT", f"/api/rules/{i}", p),
                lambda d: self.refresh())

    def _delete_rule(self) -> None:
        rule = self._selected_rule()
        if not rule:
            return
        if QMessageBox.question(self, tr("delete"),
                                f"Regel '{rule.get('name')}' löschen?") != QMessageBox.Yes:
            return
        api_client.run_async(lambda i=rule["id"]: api_client.call("DELETE", f"/api/rules/{i}"),
                             lambda d: self.refresh())


class RuleDialog(QDialog):
    def __init__(self, parent, rule: dict | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("new_rule") if not rule else tr("edit"))
        self.setMinimumWidth(460)
        lay = QVBoxLayout(self)
        form = QFormLayout()

        self.name_edit = QLineEdit(rule.get("name", "") if rule else "")
        form.addRow(tr("name"), self.name_edit)

        self.type_combo = QComboBox()
        for ident, label in RULE_TYPES:
            self.type_combo.addItem(label, ident)
        if rule:
            idx = self.type_combo.findData(rule.get("type"))
            self.type_combo.setCurrentIndex(max(0, idx))
        form.addRow(tr("type"), self.type_combo)

        self.effect = EffectPicker()
        if rule:
            self.effect.set_value(rule.get("effect", "solid"), rule.get("color", "#FF0000"))
        form.addRow(tr("effect"), self.effect)

        self.priority = QDoubleSpinBox()
        self.priority.setRange(0, 100)
        if rule:
            self.priority.setValue(float(rule.get("priority", 40)))
        else:
            self.priority.setValue(70)
        form.addRow(tr("priority"), self.priority)

        self.enabled = QCheckBox(tr("enabled"))
        self.enabled.setChecked(True if rule is None else bool(rule.get("enabled")))
        form.addRow(self.enabled)

        lay.addLayout(form)

        # params section rebuilt on type change
        self.params_host = QWidget()
        self.params_lay = QVBoxLayout(self.params_host)
        self.params_lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.params_host)
        self.type_combo.currentIndexChanged.connect(self._rebuild_params)
        self._initial_params = rule.get("params", {}) if rule else {}
        self._rebuild_params()

        buttons = QHBoxLayout()
        self.btn_ok = QPushButton(tr("save"))
        self.btn_ok.setObjectName("primary")
        self.btn_cancel = QPushButton("Abbrechen")
        buttons.addStretch(1)
        buttons.addWidget(self.btn_cancel)
        buttons.addWidget(self.btn_ok)
        lay.addLayout(buttons)
        self.btn_ok.clicked.connect(self.accept)
        self.btn_cancel.clicked.connect(self.reject)

    def _rebuild_params(self) -> None:
        rtype = self.type_combo.currentData()
        while self.params_lay.count():
            item = self.params_lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._params_form = _ParamFormWithSet(rtype, self._initial_params if rtype == getattr(self, "_last_type", None) else {})
        self._last_type = rtype
        self.params_lay.addLayout(self._params_form)

    def result_data(self) -> dict | None:
        return {
            "name": self.name_edit.text().strip() or "Regel",
            "type": self.type_combo.currentData(),
            "color": self.effect.color.color(),
            "effect": self.effect.combo.currentData(),
            "priority": int(self.priority.value()),
            "enabled": self.enabled.isChecked(),
            "params": self._params_form.params(),
        }


class _ParamFormWithSet(QFormLayout):
    """ParamForm wrapper that can prefill values from an existing rule."""

    def __init__(self, rule_type: str, params: dict) -> None:
        super().__init__()
        self.rule_type = rule_type
        self._widgets = {}
        if rule_type == "presence":
            av = QLineEdit(", ".join(params.get("availability_in", [])))
            ac = QLineEdit(", ".join(params.get("activity_in", [])))
            self._widgets = {"availability_in": av, "activity_in": ac}
            self.addRow("Verfügbarkeitswerte (z.B. Busy, DoNotDisturb)", av)
            self.addRow("Aktivitätswerte (z.B. InACall, Presenting)", ac)
        elif rule_type == "calendar":
            combo = QComboBox()
            combo.addItem("Besprechung aktiv", "meeting")
            combo.addItem("Termin naht (Puffer)", "buffer")
            combo.setCurrentIndex(1 if params.get("mode") == "buffer" else 0)
            self._widgets = {"mode": combo}
            self.addRow("Modus", combo)
        elif rule_type == "schedule":
            s = QLineEdit(params.get("start", "18:00"))
            e = QLineEdit(params.get("end", "23:59"))
            d = QLineEdit(params.get("days", "1-7"))
            self._widgets = {"start": s, "end": e, "days": d}
            self.addRow("Start (HH:MM)", s)
            self.addRow("Ende (HH:MM)", e)
            self.addRow("Tage (ISO 1=Mo … 7=So; z.B. 1-5)", d)
            self.addRow(QLabel("Modus 'off' schaltet die LED aus; Farbe wirkt sonst als Dauerlicht."))
        else:
            self.addRow(QLabel("Keine Parameter für diesen Typ."))

    def params(self) -> dict:
        out = {}
        if self.rule_type == "presence":
            av = self._widgets["availability_in"].text().strip()
            ac = self._widgets["activity_in"].text().strip()
            if av:
                out["availability_in"] = [v.strip() for v in av.split(",") if v.strip()]
            if ac:
                out["activity_in"] = [v.strip() for v in ac.split(",") if v.strip()]
        elif self.rule_type == "calendar":
            out["mode"] = self._widgets["mode"].currentData()
        elif self.rule_type == "schedule":
            out = {"start": self._widgets["start"].text().strip() or "18:00",
                   "end": self._widgets["end"].text().strip() or "23:59",
                   "days": self._widgets["days"].text().strip() or "1-7"}
        return out