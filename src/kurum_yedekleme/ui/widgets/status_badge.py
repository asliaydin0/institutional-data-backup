"""Tablo ve kartlarda durum rozeti."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget

from kurum_yedekleme.db.models import BackupStatus

_BADGE_NAMES = {
    "success": "StatusBadgeSuccess",
    "failed": "StatusBadgeFailed",
    "warning": "StatusBadgeWarning",
    "info": "StatusBadgeInfo",
    "neutral": "StatusBadgeNeutral",
}


def status_badge_widget(text: str, kind: str = "neutral") -> QWidget:
    wrapper = QWidget()
    layout = QHBoxLayout(wrapper)
    layout.setContentsMargins(4, 2, 4, 2)
    label = QLabel(text)
    label.setObjectName(_BADGE_NAMES.get(kind, "StatusBadgeNeutral"))
    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    layout.addWidget(label)
    layout.addStretch(1)
    return wrapper


def backup_status_kind(status: BackupStatus) -> str:
    if status == BackupStatus.SUCCESS:
        return "success"
    if status == BackupStatus.FAILED:
        return "failed"
    if status == BackupStatus.CANCELLED:
        return "warning"
    if status == BackupStatus.RUNNING:
        return "info"
    return "neutral"
