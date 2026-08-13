"""Yedekleme işlem ekranı."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from kurum_yedekleme.core.progress import BackupProgressEvent
from kurum_yedekleme.ui.widgets.progress_panel import ProgressPanel


class BackupPage(QWidget):
    """Manuel yedekleme ve canlı ilerleme."""

    backup_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)

        title = QLabel("Yedekleme")
        title.setObjectName("PageTitle")
        layout.addWidget(title)

        info = QLabel(
            "Yedekleme işlemi arka planda çalışır; bu ekran donmaz. "
            "Kaynak dosyalar yalnızca okunur."
        )
        info.setObjectName("Muted")
        info.setWordWrap(True)
        layout.addWidget(info)

        row = QHBoxLayout()
        self.backup_btn = QPushButton("Şimdi Yedekle")
        self.backup_btn.setObjectName("PrimaryButton")
        self.backup_btn.clicked.connect(self.backup_requested.emit)
        row.addWidget(self.backup_btn)
        row.addStretch(1)
        layout.addLayout(row)

        self.progress = ProgressPanel()
        self.progress.setVisible(True)
        layout.addWidget(self.progress)
        layout.addStretch(1)

    def set_busy(self, busy: bool) -> None:
        self.backup_btn.setEnabled(not busy)

    def apply_progress(self, event: BackupProgressEvent) -> None:
        self.progress.apply_event(event)

    def reset_progress(self) -> None:
        self.progress.reset()
        self.progress.setVisible(True)
        self.progress.apply_event(
            BackupProgressEvent(
                stage="basladi",
                message="Yedeklemeyi başlatabilirsiniz",
                percent=0,
            )
        )
