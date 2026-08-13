"""Windows system tray desteği."""

from __future__ import annotations

import os
from enum import Enum
from typing import Optional

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QMenu, QSystemTrayIcon, QWidget

from kurum_yedekleme import __app_name__


class TrayStatus(str, Enum):
    """Tray ikon durumu."""

    SUCCESS = "success"  # yeşil
    FAILED = "failed"  # kırmızı
    RUNNING = "running"  # sarı
    IDLE = "idle"  # mavi / nötr


_STATUS_COLORS = {
    TrayStatus.SUCCESS: QColor("#16a34a"),
    TrayStatus.FAILED: QColor("#dc2626"),
    TrayStatus.RUNNING: QColor("#ca8a04"),
    TrayStatus.IDLE: QColor("#1d4ed8"),
}

_STATUS_TOOLTIPS = {
    TrayStatus.SUCCESS: "Son yedekleme başarılı",
    TrayStatus.FAILED: "Son yedekleme başarısız",
    TrayStatus.RUNNING: "Yedekleme devam ediyor",
    TrayStatus.IDLE: f"{__app_name__} arka planda çalışıyor",
}


def tray_supported() -> bool:
    """Offscreen/test ortamlarında tray'i kapatır."""
    platform = os.environ.get("QT_QPA_PLATFORM", "").lower()
    if platform in {"offscreen", "minimal", "null"}:
        return False
    if os.environ.get("KURUM_YEDEKLEME_NO_TRAY") == "1":
        return False
    return QSystemTrayIcon.isSystemTrayAvailable()


def make_tray_icon(status: TrayStatus, size: int = 64) -> QIcon:
    """Duruma göre renkli yuvarlak tray ikonu üretir."""
    pixmap = QPixmap(size, size)
    pixmap.fill(QColor(0, 0, 0, 0))
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    color = _STATUS_COLORS[status]
    painter.setBrush(color)
    painter.setPen(QColor("#0f172a"))
    margin = 4
    painter.drawEllipse(margin, margin, size - 2 * margin, size - 2 * margin)
    painter.setBrush(QColor("#ffffff"))
    painter.setPen(QColor(0, 0, 0, 0))
    dot = size // 5
    painter.drawEllipse(size // 2 - dot // 2, size // 2 - dot // 2, dot, dot)
    painter.end()
    return QIcon(pixmap)


class SystemTrayManager(QObject):
    """System tray menüsü ve durum ikonu."""

    open_dashboard = Signal()
    backup_now = Signal()
    show_last_backup = Signal()
    open_settings = Signal()
    open_logs = Signal()
    quit_app = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._status = TrayStatus.IDLE
        self._enabled = tray_supported()
        self._tray: Optional[QSystemTrayIcon] = None
        self._menu: Optional[QMenu] = None

        if not self._enabled:
            return

        self._tray = QSystemTrayIcon(parent)
        self._tray.setIcon(make_tray_icon(TrayStatus.IDLE))
        self._tray.setToolTip(_STATUS_TOOLTIPS[TrayStatus.IDLE])
        self._tray.activated.connect(self._on_activated)

        menu = QMenu(parent)
        act_dashboard = QAction("Dashboard'u Aç", menu)
        act_backup = QAction("Şimdi Yedekle", menu)
        act_last = QAction("Son Yedekleme", menu)
        act_settings = QAction("Ayarlar", menu)
        act_logs = QAction("Logları Aç", menu)
        act_quit = QAction("Uygulamayı Kapat", menu)

        act_dashboard.triggered.connect(self.open_dashboard.emit)
        act_backup.triggered.connect(self.backup_now.emit)
        act_last.triggered.connect(self.show_last_backup.emit)
        act_settings.triggered.connect(self.open_settings.emit)
        act_logs.triggered.connect(self.open_logs.emit)
        act_quit.triggered.connect(self.quit_app.emit)

        menu.addAction(act_dashboard)
        menu.addAction(act_backup)
        menu.addAction(act_last)
        menu.addSeparator()
        menu.addAction(act_settings)
        menu.addAction(act_logs)
        menu.addSeparator()
        menu.addAction(act_quit)

        self._tray.setContextMenu(menu)
        self._menu = menu

    @property
    def status(self) -> TrayStatus:
        return self._status

    @property
    def is_available(self) -> bool:
        return self._enabled and self._tray is not None

    def show(self) -> None:
        if self._tray is not None:
            self._tray.show()

    def hide(self) -> None:
        if self._tray is not None:
            self._tray.hide()

    def set_status(self, status: TrayStatus, *, detail: str = "") -> None:
        self._status = status
        if self._tray is None:
            return
        self._tray.setIcon(make_tray_icon(status))
        tip = _STATUS_TOOLTIPS[status]
        if detail:
            tip = f"{tip}\n{detail}"
        self._tray.setToolTip(f"{__app_name__}\n{tip}")

    def notify(self, title: str, message: str, *, msec: int = 5000) -> None:
        if self._tray is not None and self._tray.isVisible():
            self._tray.showMessage(
                title,
                message,
                QSystemTrayIcon.MessageIcon.Information,
                msec,
            )

    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason in (
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        ):
            self.open_dashboard.emit()
