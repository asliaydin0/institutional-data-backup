"""Kurumsal arayüz teması — resmi kurum kullanımına uygun sade görünüm."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication, QDateEdit

APP_STYLESHEET = """
/* ── Genel ───────────────────────────────────────────────────────────── */
QMainWindow {
    background: #eef1f5;
}
QDialog {
    background: #f7f8fa;
    color: #1a2332;
}
* {
    font-family: "Segoe UI", "Arial", sans-serif;
    font-size: 13px;
    color: #1a2332;
}
*:disabled {
    color: #9aa5b4;
}
QWidget#ContentArea {
    background: #eef1f5;
}

/* ── Kenar çubuğu ──────────────────────────────────────────────────── */
QFrame#Sidebar {
    background: #0c2340;
    border: none;
    border-right: 1px solid #0a1c30;
}
QFrame#Sidebar QLabel {
    background: transparent;
}
QLabel#BrandEmblem {
    background: #1a4f8b;
    color: #ffffff;
    font-size: 12px;
    font-weight: 800;
    letter-spacing: 0.4px;
    border-radius: 8px;
    min-width: 46px;
    max-width: 46px;
    min-height: 46px;
    max-height: 46px;
    border: 1px solid #2a6cb8;
}
QLabel#BrandTitle {
    background: transparent;
    color: #ffffff;
    font-size: 13px;
    font-weight: 700;
    padding: 0;
    line-height: 1.2;
}
QLabel#BrandSubtitle {
    background: transparent;
    color: #8eb4dc;
    font-size: 11px;
    font-weight: 500;
    padding: 0;
}
QLabel#BrandSubtitle[testMode="true"] {
    color: #fca5a5;
    font-weight: 700;
}
QFrame#SidebarDivider {
    background: #1a3a5c;
    border: none;
    max-height: 1px;
    min-height: 1px;
}
QLabel#SidebarFooter {
    background: transparent;
    color: #5a7a9a;
    font-size: 11px;
    padding: 4px 2px;
}
QListWidget#NavList {
    background: transparent;
    border: none;
    outline: none;
    color: #b8cce0;
    padding: 4px 0;
}
QListWidget#NavList::item {
    background: transparent;
    color: #c8d8e8;
    padding: 11px 14px 11px 12px;
    margin: 2px 4px;
    border-radius: 6px;
    border-left: 3px solid transparent;
}
QListWidget#NavList::item:selected {
    background: rgba(255, 255, 255, 0.08);
    color: #ffffff;
    font-weight: 600;
    border-left: 3px solid #c8102e;
}
QListWidget#NavList::item:hover:!selected {
    background: rgba(255, 255, 255, 0.05);
    color: #e8f0f8;
}

/* ── Sayfa başlıkları ──────────────────────────────────────────────── */
QLabel#PageTitle {
    background: transparent;
    font-size: 22px;
    font-weight: 700;
    color: #0c2340;
    letter-spacing: -0.2px;
}
QLabel#PageSubtitle {
    background: transparent;
    font-size: 13px;
    color: #5c6b7f;
    margin-top: 2px;
}
QLabel#SectionTitle {
    background: transparent;
    font-size: 12px;
    font-weight: 700;
    color: #3d4f63;
    text-transform: uppercase;
    letter-spacing: 0.6px;
}

/* ── Kartlar ve paneller ───────────────────────────────────────────── */
QFrame#Card {
    background: #ffffff;
    border: 1px solid #d4dae3;
    border-radius: 8px;
}
QFrame#Card[accent="true"] {
    border-left: 3px solid #1a4f8b;
}
QFrame#SectionPanel {
    background: #ffffff;
    border: 1px solid #d4dae3;
    border-radius: 8px;
}
QLabel#CardTitle {
    background: transparent;
    color: #5c6b7f;
    font-size: 11px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}
QLabel#CardValue {
    background: transparent;
    color: #1a2332;
    font-size: 13px;
    font-weight: 600;
    line-height: 1.4;
}
QLabel#Muted, QLabel#MutedLabel {
    background: transparent;
    color: #5c6b7f;
    line-height: 1.45;
}
QLabel#StatChip {
    background: #ffffff;
    border: 1px solid #d4dae3;
    border-radius: 6px;
    padding: 7px 14px;
    font-weight: 600;
    color: #1a2332;
}
QLabel#StatChipSuccess {
    background: #f0faf4;
    border: 1px solid #b8e0c8;
    border-radius: 6px;
    padding: 7px 14px;
    font-weight: 600;
    color: #1a7f4b;
}
QLabel#StatChipFailed {
    background: #fef2f2;
    border: 1px solid #f5c2c2;
    border-radius: 6px;
    padding: 7px 14px;
    font-weight: 600;
    color: #b91c1c;
}

/* ── Durum rozetleri ───────────────────────────────────────────────── */
QLabel#StatusBadgeSuccess {
    background: #e8f5ee;
    color: #166534;
    border: 1px solid #b8e0c8;
    border-radius: 4px;
    padding: 3px 10px;
    font-size: 11px;
    font-weight: 700;
}
QLabel#StatusBadgeFailed {
    background: #fef2f2;
    color: #991b1b;
    border: 1px solid #f5c2c2;
    border-radius: 4px;
    padding: 3px 10px;
    font-size: 11px;
    font-weight: 700;
}
QLabel#StatusBadgeWarning {
    background: #fffbeb;
    color: #92400e;
    border: 1px solid #fde68a;
    border-radius: 4px;
    padding: 3px 10px;
    font-size: 11px;
    font-weight: 700;
}
QLabel#StatusBadgeInfo {
    background: #eff6ff;
    color: #1e40af;
    border: 1px solid #bfdbfe;
    border-radius: 4px;
    padding: 3px 10px;
    font-size: 11px;
    font-weight: 700;
}
QLabel#StatusBadgeNeutral {
    background: #f1f3f6;
    color: #4b5563;
    border: 1px solid #d4dae3;
    border-radius: 4px;
    padding: 3px 10px;
    font-size: 11px;
    font-weight: 700;
}

/* ── Düğmeler ──────────────────────────────────────────────────────── */
QPushButton#PrimaryButton {
    background: #1a4f8b;
    color: #ffffff;
    border: none;
    border-radius: 6px;
    padding: 9px 18px;
    font-size: 13px;
    font-weight: 600;
    min-height: 20px;
}
QPushButton#PrimaryButton:hover {
    background: #163f70;
}
QPushButton#PrimaryButton:pressed {
    background: #0c2340;
}
QPushButton#PrimaryButton:disabled {
    background: #9aa8b8;
    color: #e8ecf0;
}
QPushButton#SecondaryButton {
    background: #ffffff;
    color: #1a2332;
    border: 1px solid #c5cdd8;
    border-radius: 6px;
    padding: 9px 14px;
    font-weight: 600;
    min-height: 20px;
}
QPushButton#SecondaryButton:hover {
    background: #f4f6f8;
    border-color: #9aa8b8;
}
QPushButton#SecondaryButton:disabled {
    color: #9aa8b8;
    background: #f4f6f8;
    border-color: #e2e6ec;
}
QPushButton#DangerButton {
    background: #ffffff;
    color: #b91c1c;
    border: 1px solid #f5c2c2;
    border-radius: 6px;
    padding: 7px 14px;
    font-weight: 600;
}
QPushButton#DangerButton:hover {
    background: #fef2f2;
    border-color: #ef9a9a;
}
QPushButton#TableActionButton {
    background: #ffffff;
    color: #1a4f8b;
    border: 1px solid #c5cdd8;
    border-radius: 4px;
    padding: 2px 10px;
    font-size: 12px;
    font-weight: 600;
    min-width: 0;
}
QPushButton#TableActionButton:hover {
    background: #e8f0fa;
    border-color: #1a4f8b;
}
QPushButton#TableDangerButton {
    background: #ffffff;
    color: #b91c1c;
    border: 1px solid #f5c2c2;
    border-radius: 4px;
    padding: 2px 10px;
    font-size: 12px;
    font-weight: 600;
    min-width: 0;
}
QPushButton#TableDangerButton:hover {
    background: #fef2f2;
    border-color: #ef9a9a;
}

/* ── Form öğeleri ──────────────────────────────────────────────────── */
QLineEdit, QComboBox, QDateEdit {
    background: #ffffff;
    border: 1px solid #c5cdd8;
    border-radius: 6px;
    padding: 6px 10px;
    color: #1a2332;
    min-height: 18px;
}
QLineEdit:focus, QComboBox:focus, QDateEdit:focus,
QSpinBox:focus, QTimeEdit:focus {
    border-color: #1a4f8b;
}
QLineEdit:disabled, QComboBox:disabled, QDateEdit:disabled,
QSpinBox:disabled, QTimeEdit:disabled {
    background: #f0f2f5;
    color: #9aa5b4;
    border-color: #e2e6ec;
}
QSpinBox:disabled::up-button, QTimeEdit:disabled::up-button,
QSpinBox:disabled::down-button, QTimeEdit:disabled::down-button {
    background-color: #eef1f5;
    border-color: #e2e6ec;
}
QLabel:disabled, QLabel#Muted:disabled, QLabel#MutedLabel:disabled {
    color: #9aa5b4;
}
QComboBox::drop-down {
    border: none;
    width: 24px;
}
QComboBox QAbstractItemView {
    background: #ffffff;
    border: 1px solid #d4dae3;
    selection-background-color: #e8f0fa;
    selection-color: #0c2340;
}
QCheckBox {
    spacing: 8px;
    color: #1a2332;
}
QCheckBox::indicator {
    width: 16px;
    height: 16px;
    border-radius: 3px;
    border: 1px solid #c5cdd8;
    background: #ffffff;
}
QCheckBox::indicator:checked {
    background: #1a4f8b;
    border-color: #1a4f8b;
}
QSpinBox, QTimeEdit {
    background: #ffffff;
    border: 1px solid #c5cdd8;
    border-radius: 6px;
    color: #1a2332;
    min-height: 30px;
    padding-left: 8px;
    padding-right: 2px;
    selection-background-color: #cfe0f5;
}
QSpinBox::up-button, QTimeEdit::up-button {
    subcontrol-origin: border;
    subcontrol-position: top right;
    width: 22px;
    border: none;
    border-left: 1px solid #c5cdd8;
    background-color: #f4f6f8;
}
QSpinBox::down-button, QTimeEdit::down-button {
    subcontrol-origin: border;
    subcontrol-position: bottom right;
    width: 22px;
    border: none;
    border-left: 1px solid #c5cdd8;
    border-top: 1px solid #c5cdd8;
    background-color: #f4f6f8;
}
QSpinBox::up-button:hover, QTimeEdit::up-button:hover,
QSpinBox::down-button:hover, QTimeEdit::down-button:hover {
    background-color: #e8ecf0;
}

/* ── Tablolar ──────────────────────────────────────────────────────── */
QTableWidget {
    background: #ffffff;
    border: 1px solid #d4dae3;
    border-radius: 8px;
    gridline-color: #eef1f5;
    alternate-background-color: #f7f8fa;
    selection-background-color: #e8f0fa;
    selection-color: #0c2340;
}
QHeaderView::section {
    background: #f4f6f8;
    padding: 9px 12px;
    border: none;
    border-bottom: 2px solid #d4dae3;
    border-right: 1px solid #e8ecf0;
    font-weight: 700;
    font-size: 11px;
    color: #3d4f63;
    text-transform: uppercase;
    letter-spacing: 0.3px;
}
QTableWidget::item {
    padding: 4px 8px;
    color: #1a2332;
    background: transparent;
}
QLabel#TablePathLabel {
    background: transparent;
    color: #1a2332;
    padding: 0 4px;
}

/* ── Tooltip ve açılır pencereler ───────────────────────────────────── */
QToolTip {
    background-color: #ffffff;
    color: #1a2332;
    border: 1px solid #c5cdd8;
    padding: 6px 10px;
    border-radius: 4px;
}
QCalendarWidget {
    background: #ffffff;
    color: #1a2332;
}
QCalendarWidget QWidget {
    alternate-background-color: #f7f8fa;
    color: #1a2332;
}
QCalendarWidget QWidget#qt_calendar_navigationbar {
    background: #f4f6f8;
    border-bottom: 1px solid #d4dae3;
}
QCalendarWidget QToolButton {
    background: #ffffff;
    color: #1a2332;
    border: 1px solid #c5cdd8;
    border-radius: 4px;
    padding: 4px 8px;
    font-weight: 600;
}
QCalendarWidget QToolButton:hover {
    background: #e8f0fa;
    border-color: #1a4f8b;
}
QCalendarWidget QMenu {
    background: #ffffff;
    color: #1a2332;
    border: 1px solid #d4dae3;
}
QCalendarWidget QSpinBox {
    background: #ffffff;
    color: #1a2332;
    border: 1px solid #c5cdd8;
}
QCalendarWidget QAbstractItemView:enabled {
    background: #ffffff;
    color: #1a2332;
    selection-background-color: #1a4f8b;
    selection-color: #ffffff;
}
QCalendarWidget QAbstractItemView:disabled {
    color: #9aa8b8;
}

/* ── İlerleme ve durum çubuğu ──────────────────────────────────────── */
QProgressBar {
    border: 1px solid #d4dae3;
    border-radius: 6px;
    background: #eef1f5;
    text-align: center;
    min-height: 18px;
    max-height: 18px;
    color: #1a2332;
    font-size: 11px;
    font-weight: 600;
}
QProgressBar::chunk {
    background: #1a4f8b;
    border-radius: 5px;
}
QStatusBar {
    background: #e2e6ec;
    color: #3d4f63;
    border-top: 1px solid #d4dae3;
    font-size: 12px;
}
QStatusBar::item {
    border: none;
}

/* ── Log görüntüleyici ─────────────────────────────────────────────── */
QTextEdit {
    background: #ffffff;
    border: 1px solid #d4dae3;
    border-radius: 8px;
    color: #1a2332;
}

/* ── Test modu ─────────────────────────────────────────────────────── */
QLabel#TestModeBanner {
    background: #7f1d1d;
    color: #fef2f2;
    font-size: 13px;
    font-weight: 700;
    padding: 10px 16px;
    border-radius: 6px;
    border: 1px solid #991b1b;
    letter-spacing: 0.2px;
}

/* ── Hakkında sayfası ──────────────────────────────────────────────── */
QLabel#AboutVersion {
    background: transparent;
    font-size: 15px;
    font-weight: 700;
    color: #0c2340;
}
QLabel#AboutCredit {
    background: transparent;
    font-size: 11px;
    color: #8b97a8;
}
"""


def apply_app_theme(app: QApplication) -> None:
    """Tüm pencere, tooltip ve takvim popup'larına kurumsal tema uygular."""
    app.setStyle("Fusion")
    app.setStyleSheet(APP_STYLESHEET)

    palette = app.palette()
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor("#ffffff"))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor("#1a2332"))
    palette.setColor(QPalette.ColorRole.Window, QColor("#eef1f5"))
    palette.setColor(QPalette.ColorRole.WindowText, QColor("#1a2332"))
    palette.setColor(QPalette.ColorRole.Base, QColor("#ffffff"))
    palette.setColor(QPalette.ColorRole.Text, QColor("#1a2332"))
    palette.setColor(QPalette.ColorRole.Button, QColor("#f4f6f8"))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor("#1a2332"))
    palette.setColor(QPalette.ColorRole.Highlight, QColor("#1a4f8b"))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
    app.setPalette(palette)


def style_date_edit(widget: QDateEdit) -> None:
    """Tarih seçici takvimini açık temaya zorlar."""
    cal = widget.calendarWidget()
    cal.setFirstDayOfWeek(Qt.DayOfWeek.Monday)
    pal = cal.palette()
    pal.setColor(QPalette.ColorRole.Window, QColor("#ffffff"))
    pal.setColor(QPalette.ColorRole.WindowText, QColor("#1a2332"))
    pal.setColor(QPalette.ColorRole.Base, QColor("#ffffff"))
    pal.setColor(QPalette.ColorRole.Text, QColor("#1a2332"))
    pal.setColor(QPalette.ColorRole.Button, QColor("#f4f6f8"))
    pal.setColor(QPalette.ColorRole.ButtonText, QColor("#1a2332"))
    pal.setColor(QPalette.ColorRole.Highlight, QColor("#1a4f8b"))
    pal.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
    cal.setPalette(pal)
