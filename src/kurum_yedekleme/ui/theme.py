"""Kurumsal arayüz teması (sade, modern)."""

APP_STYLESHEET = """
QMainWindow {
    background: #f1f5f9;
}
QDialog {
    background: #f8fafc;
    color: #0f172a;
}
* {
    font-family: "Segoe UI", "Arial", sans-serif;
    font-size: 13px;
    color: #0f172a;
}
QFrame#Sidebar {
    background: #0f172a;
    border: none;
}
QFrame#Sidebar QLabel {
    background: transparent;
}
QLabel#BrandTitle {
    background: transparent;
    color: #f8fafc;
    font-size: 17px;
    font-weight: 700;
    padding: 2px 4px;
}
QLabel#BrandSubtitle {
    background: transparent;
    color: #fbbf24;
    font-size: 11px;
    font-weight: 600;
    padding: 2px 4px;
}
QListWidget#NavList {
    background: transparent;
    border: none;
    outline: none;
    color: #cbd5e1;
    padding: 8px 0;
}
QListWidget#NavList::item {
    background: transparent;
    color: #cbd5e1;
    padding: 12px 14px;
    margin: 3px 6px;
    border-radius: 8px;
}
QListWidget#NavList::item:selected {
    background: #1d4ed8;
    color: #ffffff;
    font-weight: 600;
}
QListWidget#NavList::item:hover:!selected {
    background: #1e293b;
    color: #f1f5f9;
}
QFrame#Card {
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 12px;
}
QLabel#CardTitle {
    background: transparent;
    color: #64748b;
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.4px;
}
QLabel#CardValue {
    background: transparent;
    color: #0f172a;
    font-size: 13px;
    font-weight: 600;
}
QLabel#PageTitle {
    background: transparent;
    font-size: 24px;
    font-weight: 700;
    color: #0f172a;
}
QLabel#Muted, QLabel#MutedLabel {
    background: transparent;
    color: #64748b;
}
QPushButton#PrimaryButton {
    background: #1d4ed8;
    color: white;
    border: none;
    border-radius: 10px;
    padding: 10px 18px;
    font-size: 14px;
    font-weight: 700;
    min-height: 20px;
}
QPushButton#PrimaryButton:hover {
    background: #1e40af;
}
QPushButton#PrimaryButton:disabled {
    background: #94a3b8;
}
QPushButton#SecondaryButton {
    background: #e2e8f0;
    color: #0f172a;
    border: none;
    border-radius: 8px;
    padding: 10px 14px;
    font-weight: 600;
    min-height: 20px;
}
QPushButton#SecondaryButton:hover {
    background: #cbd5e1;
}
QPushButton#SecondaryButton:disabled {
    color: #94a3b8;
    background: #f1f5f9;
}
QPushButton#DangerButton {
    background: #fee2e2;
    color: #991b1b;
    border: none;
    border-radius: 8px;
    padding: 8px 14px;
    font-weight: 600;
}
QProgressBar {
    border: 1px solid #e2e8f0;
    border-radius: 8px;
    background: #e2e8f0;
    text-align: center;
    min-height: 18px;
    max-height: 18px;
    color: #0f172a;
}
QProgressBar::chunk {
    background: #2563eb;
    border-radius: 7px;
}
QTableWidget {
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 8px;
    gridline-color: #f1f5f9;
    alternate-background-color: #f8fafc;
}
QHeaderView::section {
    background: #f8fafc;
    padding: 8px 10px;
    border: none;
    border-bottom: 1px solid #e2e8f0;
    border-right: 1px solid #e2e8f0;
    font-weight: 600;
    color: #334155;
}
QLineEdit, QListWidget#SourceList, QComboBox {
    background: #ffffff;
    border: 1px solid #cbd5e1;
    border-radius: 8px;
    padding: 6px 8px;
    color: #0f172a;
}
/* Spin/Time: agresif padding ok tıklamasını bozar; subcontrol ile düzeltilir */
QSpinBox, QTimeEdit {
    background: #ffffff;
    border: 1px solid #cbd5e1;
    border-radius: 6px;
    color: #0f172a;
    min-height: 30px;
    padding-left: 8px;
    padding-right: 2px;
    selection-background-color: #bfdbfe;
}
QSpinBox::up-button, QTimeEdit::up-button {
    subcontrol-origin: border;
    subcontrol-position: top right;
    width: 24px;
    border: none;
    border-left: 1px solid #cbd5e1;
    background-color: #e2e8f0;
}
QSpinBox::down-button, QTimeEdit::down-button {
    subcontrol-origin: border;
    subcontrol-position: bottom right;
    width: 24px;
    border: none;
    border-left: 1px solid #cbd5e1;
    border-top: 1px solid #cbd5e1;
    background-color: #e2e8f0;
}
QSpinBox::up-button:hover, QTimeEdit::up-button:hover,
QSpinBox::down-button:hover, QTimeEdit::down-button:hover {
    background-color: #cbd5e1;
}
QSpinBox::up-button:pressed, QTimeEdit::up-button:pressed,
QSpinBox::down-button:pressed, QTimeEdit::down-button:pressed {
    background-color: #94a3b8;
}
QSpinBox::up-arrow, QTimeEdit::up-arrow {
    width: 10px;
    height: 10px;
}
QSpinBox::down-arrow, QTimeEdit::down-arrow {
    width: 10px;
    height: 10px;
}
QStatusBar {
    background: #e2e8f0;
    color: #334155;
}
QLabel#TestModeBanner {
    background: #7f1d1d;
    color: #fef2f2;
    font-size: 14px;
    font-weight: 800;
    padding: 10px 16px;
    border-radius: 10px;
    letter-spacing: 0.3px;
}
QTextEdit {
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 8px;
    color: #0f172a;
}
"""
