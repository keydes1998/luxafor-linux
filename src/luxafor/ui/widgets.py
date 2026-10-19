"""Reusable widgets: cards, color button, badges and helpers."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox, QColorDialog, QComboBox, QDoubleSpinBox, QFormLayout, QFrame,
    QHBoxLayout, QLabel, QLineEdit, QPushButton, QSpinBox, QTableWidget,
    QTableWidgetItem, QTextEdit, QVBoxLayout, QWidget,
)

from luxafor.ui.i18n import tr

PALETTE = ["#00B030", "#FFD75E", "#FFA500", "#FF0000", "#8B0000", "#FF0044",
           "#2979FF", "#7C4DFF", "#FFFFFF", "#000000", "#123ABC", "#00FFAA"]


def hline() -> QFrame:
    f = QFrame()
    f.setFrameShape(QFrame.HLine)
    f.setStyleSheet("border:none; border-top:1px solid #242834; max-height:1px;")
    return f


class Card(QFrame):
    """Rounded card container with optional title row and content layout."""

    def __init__(self, title: str | None = None) -> None:
        super().__init__()
        self.setObjectName("Card")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(10)
        self.title_lbl = None
        self.lay = lay
        if title:
            t = QLabel(title.upper())
            t.setObjectName("cardTitle")
            self.title_lbl = t
            lay.addWidget(t)

    # small conveniences so callers can treat Card like its layout
    def add(self, widget: QWidget) -> QWidget:
        self.lay.addWidget(widget)
        return widget

    def addLayout(self, layout) -> None:  # noqa: N802
        self.lay.addLayout(layout)

    def addStretch(self, stretch: int = 0) -> None:  # noqa: N802
        self.lay.addStretch(stretch)

    def row(self, *widgets) -> None:
        box = QHBoxLayout()
        box.setSpacing(8)
        for w in widgets:
            box.addWidget(w, 1 if w is widgets[0] else 0)
        self.lay.addLayout(box)


class ColorButton(QPushButton):
    color_changed = Signal(str)

    def __init__(self, color: str = "#FF0000") -> None:
        super().__init__()
        self._color = color
        self.setFixedSize(52, 34)
        self._update()
        self.clicked.connect(self._pick)

    def _update(self) -> None:
        self.setStyleSheet(f"background: {self._color}; border:1px solid #2C313D; border-radius:8px;")

    def _pick(self) -> None:
        c = QColorDialog.getColor(QColor(self._color), self, tr("color"))
        if c.isValid():
            self.set_color(c.name().upper())
            self.color_changed.emit(self._color)

    def set_color(self, color: str) -> None:
        self._color = color
        self._update()

    def color(self) -> str:
        return self._color


class ColorEdit(QWidget):
    """Inline-Farbwahl: Palette + Hex-Eingabe + Vorschau (WM-unabhängig)."""

    color_changed = Signal(str)

    def __init__(self, color: str = "#FF0000", columns: int = 12) -> None:
        super().__init__()
        self._color = color
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)

        grid = QVBoxLayout()
        grid.setSpacing(4)
        row1 = QHBoxLayout()
        row2 = QHBoxLayout()
        self._swatches: list[QPushButton] = []
        for i, c in enumerate(PALETTE):
            b = QPushButton()
            b.setFixedSize(26, 22)
            b.setStyleSheet(f"background:{c}; border:1px solid #2C313D; border-radius:6px;"
                            "padding:0;")
            b.setToolTip(c)
            b.clicked.connect(lambda _=False, col=c: self.set_color(col))
            if i < 6:
                row1.addWidget(b)
            else:
                row2.addWidget(b)
            self._swatches.append(b)
        row1.addStretch(1)
        row2.addStretch(1)
        grid.addLayout(row1)
        grid.addLayout(row2)
        lay.addLayout(grid, 1)

        col2 = QVBoxLayout()
        col2.setSpacing(4)
        self.preview = QPushButton()
        self.preview.setFixedSize(44, 24)
        self.preview.setEnabled(False)
        col2.addWidget(self.preview)
        self.hex_edit = QLineEdit(color)
        self.hex_edit.setFixedWidth(86)
        self.hex_edit.setPlaceholderText("#RRGGBB")
        self.hex_edit.editingFinished.connect(self._from_hex)
        col2.addWidget(self.hex_edit)
        col2.addStretch(1)
        lay.addLayout(col2)
        self.apply_style()

    def apply_style(self) -> None:
        self.preview.setStyleSheet(
            f"background:{self._color}; border:1px solid #2C313D; border-radius:8px;"
            "padding:0;")
        # aktive Swatch hervorheben
        for i, b in enumerate(self._swatches):
            active = (PALETTE[i].upper() == self._color.upper())
            b.setStyleSheet(
                f"background:{PALETTE[i]}; border:{'2px solid #FFFFFF' if active else '1px solid #2C313D'};"
                "border-radius:6px; padding:0;")

    def set_color(self, color: str) -> None:
        try:
            from luxafor.hardware.base import parse_color, format_color
            color = format_color(parse_color(color))
        except (ValueError, TypeError):
            color = self._color
        if color != self._color:
            self._color = color
            self.apply_style()
            self.color_changed.emit(self._color)

    def _from_hex(self) -> None:
        v = self.hex_edit.text().strip()
        self.set_color(v if v.startswith("#") else "#" + v)
        self.hex_edit.setText(self._color)

    def color(self) -> str:
        return self._color


class ColorPill(QWidget):
    """Live LED color preview swatch with a soft glow look."""

    def __init__(self, size: int = 84) -> None:
        super().__init__()
        self._size = size
        self._color = "#101218"
        self.setFixedSize(size, size)
        self._lbl = QLabel(self)
        self._lbl.setAlignment(Qt.AlignCenter)
        self._lbl.setStyleSheet("background:transparent; color:#9AA3B2; font-size:10px;")
        self._lbl.setFixedSize(size, size)

    def set_color(self, color: str, label: str = "") -> None:
        self._color = color if (color.startswith("#") and len(color) in (4, 7)) else "#101218"
        self._lbl.setText(label or "")
        self._lbl.setStyleSheet(
            f"background:transparent; color:#9AA3B2; font-size:10px;"
            f"background-color: rgba(0,0,0,120);")
        self._lbl.raise_()
        self.update()

    def paintEvent(self, ev) -> None:  # noqa: N802
        from PySide6.QtGui import QPainter, QBrush, QPen
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = self._size // 2 - 8
        for glow, alpha in ((r + 9, 55), (r + 4, 90)):
            p.setPen(Qt.NoPen)
            c = QColor(self._color)
            c.setAlpha(alpha)
            p.setBrush(QBrush(c))
            p.drawEllipse(self.rect().center(), glow, glow)
        p.setBrush(QBrush(QColor(self._color)))
        p.setPen(QPen(QColor("#2C313D"), 1))
        p.drawEllipse(self.rect().center(), r, r)
        p.end()


class Badge(QLabel):
    OK, WARN, ERR, MUTED = ("ok", "warn", "err", "muted")

    def __init__(self, text: str = "", kind: str = "muted") -> None:
        super().__init__(text)
        self.set_kind(kind)

    def set_kind(self, kind: str) -> None:
        colors = {
            "ok": ("#12251A", "#3DDC84"),
            "warn": ("#2A2410", "#FFD75E"),
            "err": ("#2A1315", "#FF6D6D"),
            "muted": ("#1B1E25", "#9AA3B2"),
        }
        bg, fg = colors.get(kind, colors["muted"])
        self.setStyleSheet(
            f"background:{bg}; color:{fg}; border-radius:8px; padding:3px 10px;"
            "font-size:11px; font-weight:600;")
        self.setText(self.text())


def form_row(form: QFormLayout, label_key: str, widget: QWidget) -> QWidget:
    form.addRow(tr(label_key), widget)
    return widget


class EffectPicker(QWidget):
    """Combines effect base + color edit into one widget."""

    def __init__(self, with_color: bool = True) -> None:
        super().__init__()
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.combo = QComboBox()
        for ident, label in [("solid", "Dauerlicht"), ("off", "Aus"),
                             ("strobe:4", "Blinken"), ("wave:2", "Welle"),
                             ("pattern:4", "Pattern")]:
            self.combo.addItem(label, ident)
        lay.addWidget(self.combo, 1)
        self.color = ColorEdit() if with_color else None
        if self.color:
            lay.addWidget(self.color)

    def value(self) -> tuple[str, str]:
        return self.combo.currentData(), (self.color.color() if self.color else "#FF0000")

    def set_value(self, effect: str, color: str) -> None:
        idx = self.combo.findData(effect)
        if idx < 0:
            idx = self.combo.findData(effect.split(":")[0] + ":4")
        self.combo.setCurrentIndex(max(0, idx))
        if self.color:
            self.color.set_color(color)


def make_table(columns: list[str], rows_data: list[list], stretch_last: bool = True) -> QTableWidget:
    t = QTableWidget(len(rows_data), len(columns))
    t.setHorizontalHeaderLabels(columns)
    t.verticalHeader().setVisible(False)
    t.setAlternatingRowColors(True)
    t.setSelectionBehavior(QTableWidget.SelectRows)
    t.setEditTriggers(QTableWidget.NoEditTriggers)
    for i, row in enumerate(rows_data):
        for j, val in enumerate(row):
            item = QTableWidgetItem("" if val is None else str(val))
            t.setItem(i, j, item)
    if columns:
        t.horizontalHeader().setStretchLastSection(stretch_last)
    return t


class ParamForm(QFormLayout):
    """Builds a small editor for rule params by type with sensible defaults."""

    def __init__(self, rule_type: str, params: dict) -> None:
        super().__init__()
        self.rule_type = rule_type
        self._widgets = {}
        if rule_type == "presence":
            self._widgets["availability_in"] = QLineEdit(
                ", ".join(params.get("availability_in", [])))
            self._widgets["activity_in"] = QLineEdit(
                ", ".join(params.get("activity_in", [])))
            self.addRow("Verfügbarkeitswerte (Komma)", self._widgets["availability_in"])
            self.addRow("Aktivitätswerte (Komma)", self._widgets["activity_in"])
        elif rule_type == "calendar":
            w = QComboBox()
            w.addItem("Besprechung aktiv", "meeting")
            w.addItem("Termin naht (Puffer)", "buffer")
            w.setCurrentIndex(0 if params.get("mode", "meeting") == "meeting" else 1)
            self._widgets["mode"] = w
            self.addRow("Modus", w)
        elif rule_type == "schedule":
            s = QLineEdit(str(params.get("start", "18:00")))
            e = QLineEdit(str(params.get("end", "23:59")))
            d = QLineEdit(str(params.get("days", "1-7")))
            self._widgets.update({"start": s, "end": e, "days": d})
            self.addRow("Start (HH:MM)", s)
            self.addRow("Ende (HH:MM)", e)
            self.addRow("Tage (ISO 1-7, z.B. 1-5)", d)
        elif rule_type in ("idle", "lock", "webhook", "manual"):
            self.addRow(QLabel(tr("params") + ": keine für diesen Typ"))

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


class Toggle(QCheckBox):
    def value(self) -> bool:
        return self.isChecked()

    def set_value(self, v: bool) -> None:
        self.setChecked(bool(v))


def text_spin(mn=0, mx=99999, val=0, suffix_min=True) -> QSpinBox:
    w = QSpinBox()
    w.setRange(mn, mx)
    w.setValue(int(val))
    if suffix_min:
        w.setSuffix(" min")
    return w


def seconds_spin(val=60, mn=20, mx=3600) -> QSpinBox:
    w = QSpinBox()
    w.setRange(mn, mx)
    w.setValue(int(val))
    w.setSuffix(" s")
    return w


class LogView(QTextEdit):
    def __init__(self) -> None:
        super().__init__()
        self.setReadOnly(True)
        self.setFont(self._mono())

    @staticmethod
    def _mono():
        from PySide6.QtGui import QFontDatabase
        f = QFontDatabase.systemFont(QFontDatabase.FixedFont)
        f.setPointSize(9)
        return f

    def append_lines(self, lines: list[str]) -> None:
        self.setPlainText("\n".join(lines))
        from PySide6.QtGui import QTextCursor
        self.moveCursor(QTextCursor.End)

class ToggleRow(QWidget):
    """Checkbox row used inside QFormLayouts."""

    def __init__(self, label: str) -> None:
        super().__init__()
        from PySide6.QtWidgets import QCheckBox
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.checkbox = QCheckBox(label)
        lay.addWidget(self.checkbox)
        self._user_touched = False
        self.checkbox.toggled.connect(self._mark)

    def _mark(self, v: bool) -> None:
        self._user_touched = True

    def isChecked(self) -> bool:  # noqa: N802
        return self.checkbox.isChecked()

    def setChecked(self, v: bool) -> None:  # noqa: N802
        self.checkbox.blockSignals(True)   # programmatic changes are not user edits
        self.checkbox.setChecked(bool(v))
        self.checkbox.blockSignals(False)
