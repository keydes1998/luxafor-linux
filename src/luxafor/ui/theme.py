"""Qt style sheets: modern SaaS-dashboard look with dark and light modes."""
from __future__ import annotations

DARK = """
QWidget { background-color: #15171C; color: #E6E8EE; font-size: 13px; }
QMainWindow, #sidebar { background-color: #0F1115; }
#brand { font-size: 18px; font-weight: 600; padding: 18px 12px 8px; }
#nav QListWidget { background: transparent; border: none; outline: 0; }
#nav QListWidget::item { padding: 10px 14px; border-radius: 10px; margin: 4px 8px; color: #9AA3B2; }
#nav QListWidget::item:selected { background: #23262E; color: #FFFFFF; }
#nav QListWidget::item:hover { background: #1B1E25; }
#content { background-color: #15171C; }
Card { background-color: #1B1E25; border: 1px solid #242834; border-radius: 14px; }
Card QLabel#cardTitle { font-weight: 600; color: #9AA3B2; font-size: 11px; letter-spacing: 1px; }
QLabel#h1 { font-size: 22px; font-weight: 650; }
QLabel#muted { color: #9AA3B2; }
QPushButton { background: #23262E; border: 1px solid #2C313D; border-radius: 10px;
              padding: 8px 14px; color: #E6E8EE; }
QPushButton:hover { background: #2B303B; }
QPushButton:disabled { color: #5A6272; background: #1B1E25; }
QPushButton#primary { background: #2979FF; border-color: #2979FF; color: white; font-weight: 600; }
QPushButton#primary:hover { background: #3B8AFF; }
QPushButton#danger { background: #D32F2F; border-color: #D32F2F; color: white; }
QPushButton#ok { background: #188038; border-color: #188038; color: white; }
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QTimeEdit, QTextEdit {
    background: #101218; border: 1px solid #2C313D; border-radius: 8px; padding: 7px 10px;
    selection-background-color: #2979FF; }
QLineEdit:focus, QComboBox:focus, QSpinBox:focus { border-color: #2979FF; }
QTableWidget { background: #161921; border: 1px solid #242834; border-radius: 10px;
               gridline-color: #242834; alternate-background-color: #191C24; }
QHeaderView::section { background: #1B1E25; color: #9AA3B2; border: none; padding: 8px; }
QListWidget { background: #161921; border: 1px solid #242834; border-radius: 10px; }
QTabWidget::pane { border: 1px solid #242834; border-radius: 10px; }
QTabBar::tab { background: #161921; color: #9AA3B2; padding: 8px 16px; border-radius: 8px; margin: 2px; }
QTabBar::tab:selected { background: #23262E; color: white; }
QSlider::groove:horizontal { height: 6px; background: #2C313D; border-radius: 3px; }
QSlider::handle:horizontal { background: #2979FF; width: 16px; height: 16px; margin: -5px 0;
                             border-radius: 8px; }
QCheckBox { spacing: 8px; }
QProgressBar { border: none; background: #1B1E25; border-radius: 4px; height: 8px; }
QProgressBar::chunk { background: #2979FF; border-radius: 4px; }
QToolTip { background: #1B1E25; color: #E6E8EE; border: 1px solid #2C313D; padding: 4px; }
QScrollBar:vertical { background: transparent; width: 10px; margin: 2px; }
QScrollBar::handle:vertical { background: #2C313D; border-radius: 5px; min-height: 30px; }
QScrollBar::add-line, QScrollBar::sub-line { height: 0; }
QMenu { background: #1B1E25; border: 1px solid #2C313D; border-radius: 10px; padding: 6px; }
QMenu::item { padding: 8px 18px; border-radius: 8px; }
QMenu::item:selected { background: #2979FF; }
"""

LIGHT = """
QWidget { background-color: #F5F6F8; color: #1B1C22; font-size: 13px; }
QMainWindow, #sidebar { background-color: #FFFFFF; }
#brand { font-size: 18px; font-weight: 600; padding: 18px 12px 8px; }
#nav QListWidget { background: transparent; border: none; outline: 0; }
#nav QListWidget::item { padding: 10px 14px; border-radius: 10px; margin: 4px 8px; color: #55596A; }
#nav QListWidget::item:selected { background: #E8ECF5; color: #101740; }
#nav QListWidget::item:hover { background: #F0F2F7; }
#content { background-color: #F5F6F8; }
Card { background-color: #FFFFFF; border: 1px solid #E4E7EE; border-radius: 14px; }
Card QLabel#cardTitle { font-weight: 600; color: #7A8194; font-size: 11px; letter-spacing: 1px; }
QLabel#h1 { font-size: 22px; font-weight: 650; }
QLabel#muted { color: #7A8194; }
QPushButton { background: #EDF0F6; border: 1px solid #DCE1EC; border-radius: 10px; padding: 8px 14px; }
QPushButton:hover { background: #E3E8F3; }
QPushButton:disabled { color: #A2A8BC; }
QPushButton#primary { background: #2979FF; border-color: #2979FF; color: white; font-weight: 600; }
QPushButton#primary:hover { background: #3B8AFF; }
QPushButton#danger { background: #D32F2F; border-color: #D32F2F; color: white; }
QPushButton#ok { background: #188038; border-color: #188038; color: white; }
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QTextEdit {
    background: #FFFFFF; border: 1px solid #DCE1EC; border-radius: 8px; padding: 7px 10px; }
QLineEdit:focus, QComboBox:focus, QSpinBox:focus { border-color: #2979FF; }
QTableWidget { background: #FFFFFF; border: 1px solid #E4E7EE; border-radius: 10px;
               gridline-color: #E4E7EE; alternate-background-color: #F8F9FC; }
QHeaderView::section { background: #F0F2F7; color: #55596A; border: none; padding: 8px; }
QListWidget { background: #FFFFFF; border: 1px solid #E4E7EE; border-radius: 10px; }
QSlider::groove:horizontal { height: 6px; background: #DCE1EC; border-radius: 3px; }
QSlider::handle:horizontal { background: #2979FF; width: 16px; margin: -5px 0; border-radius: 8px; }
QToolTip { background: #1B1C22; color: #FFFFFF; border: none; padding: 4px; }
QMenu { background: #FFFFFF; border: 1px solid #DCE1EC; border-radius: 10px; padding: 6px; }
QMenu::item { padding: 8px 18px; border-radius: 8px; }
QMenu::item:selected { background: #2979FF; }
"""


def stylesheet(theme: str) -> str:
    return DARK if theme != "light" else LIGHT