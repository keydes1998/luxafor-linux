"""Devices page: per-device control, zones, effects, brightness, test."""
from __future__ import annotations

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QComboBox, QGridLayout, QHBoxLayout, QLabel, QScrollArea, QSlider,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget, QPushButton,
)

from luxafor.ui import api_client
from luxafor.ui.i18n import tr
from luxafor.ui.widgets import Card, ColorEdit, hline


class DevicesPage(QWidget):
    def __init__(self) -> None:
        super().__init__()
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(16)

        title = QLabel(tr("Devices"))
        title.setObjectName("h1")
        root.addWidget(title)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        inner = QWidget()
        scroll.setWidget(inner)
        v = QVBoxLayout(inner)
        v.setSpacing(14)
        root.addWidget(scroll)

        # control card ----------------------------------------------------------
        ctl = Card(tr("color") + " / " + tr("effect"))
        grid = QGridLayout()
        ctl.lay.addLayout(grid)

        self.device_combo = QComboBox()
        self.zone_combo = QComboBox()
        for zone, label in [("all", "Alle"), ("front", "Vorderseite"), ("back", "Rückseite"),
                            ("1", "LED 1"), ("2", "LED 2"), ("3", "LED 3"),
                            ("4", "LED 4"), ("5", "LED 5"), ("6", "LED 6")]:
            self.zone_combo.addItem(label, zone)
        self.color_edit = ColorEdit("#FF0000")
        self.effect_combo = QComboBox()
        for ident, label in [("solid", "Dauerlicht"), ("strobe:4", "Blinken"),
                             ("wave:2", "Welle"), ("pattern:4", "Pattern")]:
            self.effect_combo.addItem(label, ident)

        grid.addWidget(QLabel("Gerät"), 0, 0)
        grid.addWidget(self.device_combo, 0, 1)
        grid.addWidget(QLabel(tr("zone")), 0, 2)
        grid.addWidget(self.zone_combo, 0, 3)
        grid.addWidget(QLabel(tr("color")), 1, 0)
        grid.addWidget(self.color_edit, 1, 1)
        grid.addWidget(QLabel(tr("effect")), 1, 2)
        grid.addWidget(self.effect_combo, 1, 3)

        actions = QHBoxLayout()
        self.btn_set = QPushButton(tr("color") + " setzen")
        self.btn_set.setObjectName("primary")
        self.btn_off = QPushButton(tr("led_off"))
        self.btn_test = QPushButton(tr("device_test"))
        self.btn_flash = QPushButton("Blitztest")
        actions.addWidget(self.btn_set)
        actions.addWidget(self.btn_off)
        actions.addWidget(self.btn_test)
        actions.addWidget(self.btn_flash)
        actions.addStretch(1)
        ctl.lay.addLayout(actions)

        # brightness (software dimming; Flag protocol has no brightness command)
        bright_box = QHBoxLayout()
        self.brightness = QSlider()
        self.brightness.setRange(5, 100)
        self.brightness.setValue(100)
        self.lbl_bright = QLabel(f"{tr('brightness')}: 100 %")
        self.lbl_bright.setObjectName("muted")
        bright_box.addWidget(QLabel(tr("brightness") + " (Software-Dämpfung)"))
        bright_box.addWidget(self.brightness, 1)
        bright_box.addWidget(self.lbl_bright)
        ctl.lay.addLayout(bright_box)
        self.brightness.valueChanged.connect(
            lambda v: (self.lbl_bright.setText(f"{tr('brightness')}: {v} %")))
        self.brightness.sliderReleased.connect(self._save_brightness)

        v.addWidget(ctl)

        # device table -----------------------------------------------------------
        table_card = Card(tr("devices_connected"))
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(
            ["ID", "Modell", tr("color"), "Verbindung", "Fehler"])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.horizontalHeader().setStretchLastSection(True)
        table_card.add(self.table)
        v.addWidget(table_card)

        self.info_lbl = QLabel("")
        self.info_lbl.setObjectName("muted")
        self.info_lbl.setWordWrap(True)
        v.addWidget(self.info_lbl)

        self.btn_set.clicked.connect(self._set_color)
        self.btn_off.clicked.connect(self._off)
        self.btn_test.clicked.connect(self._test)
        self.btn_flash.clicked.connect(self._flash)

        self.timer = QTimer(self)
        self.timer.setInterval(4000)
        self.timer.timeout.connect(self.refresh)
        self.timer.start()
        self.refresh()

    # -- helpers ------------------------------------------------------------------
    def _selected_device(self):
        return self.device_combo.currentData() or None

    def refresh(self) -> None:
        api_client.run_async(lambda: api_client.call("GET", "/api/devices"), self._apply)
        api_client.run_async(lambda: api_client.call("GET", "/api/devices/supported"),
                             self._apply_supported)

    def _apply(self, data: dict) -> None:
        if data.get("_unreachable"):
            return
        current = self.device_combo.currentData()
        self.device_combo.blockSignals(True)
        self.device_combo.clear()
        for d in data.get("devices", []):
            self.device_combo.addItem(d.get("model", "?"), d.get("id"))
        if current:
            idx = self.device_combo.findData(current)
            if idx >= 0:
                self.device_combo.setCurrentIndex(idx)
        self.device_combo.blockSignals(False)

        devices = data.get("devices", [])
        self.table.setRowCount(len(devices))
        for i, d in enumerate(devices):
            self.table.setItem(i, 0, QTableWidgetItem(str(d.get("id", ""))))
            self.table.setItem(i, 1, QTableWidgetItem(str(d.get("model", ""))))
            self.table.setItem(i, 2, QTableWidgetItem(str(d.get("color", ""))))
            self.table.setItem(i, 3, QTableWidgetItem("offen" if d.get("open") else "geschlossen"))
            self.table.setItem(i, 4, QTableWidgetItem(str(d.get("error") or "")))
        effects = {e["id"]: e for e in data.get("effects", [])}
        pass

    def _apply_supported(self, data: dict) -> None:
        if data.get("_unreachable"):
            return
        lines = [f"Verifiziert: {', '.join(v['model'] for v in data.get('verified', []))}",
                 f"Vendor-ID: {data.get('vendor_id')}"]
        for n in data.get("notes", []):
            lines.append("– " + n)
        self.info_lbl.setText("\n".join(lines))

    def _set_color(self) -> None:
        payload = {"led": self.zone_combo.currentData(),
                   "color": self.color_edit.color(),
                   "effect": self.effect_combo.currentData()}
        if self.device_combo.currentData():
            payload["device"] = self.device_combo.currentData()
        effect = payload.pop("effect")
        path = "/api/device/color" if effect == "solid" else "/api/device/effect"
        payload["effect"] = effect
        api_client.run_async(lambda p=payload, pp=path: api_client.call("POST", pp, p),
                             lambda _: self.refresh())

    def _off(self) -> None:
        did = self.device_combo.currentData()
        api_client.run_async(lambda d=did: api_client.call("POST", "/api/device/off", {"device": d}),
                             lambda _: self.refresh())

    def _test(self) -> None:
        did = self.device_combo.currentData()
        api_client.run_async(lambda d=did: api_client.call("POST", "/api/device/test", {"device": d}),
                             lambda _: self.refresh())

    def _flash(self) -> None:
        did = self.device_combo.currentData()
        api_client.run_async(
            lambda d=did: api_client.call("POST", "/api/device/flash",
                                          {"color": self.color_edit.color(), "duration": 3,
                                           "effect": "strobe:4", "device": d}),
            lambda _: self.refresh())

    def _save_brightness(self) -> None:
        val = self.brightness.value()
        api_client.run_async(
            lambda: api_client.call("PUT", "/api/settings", {"hardware.brightness": str(val)}),
            lambda _d: None)