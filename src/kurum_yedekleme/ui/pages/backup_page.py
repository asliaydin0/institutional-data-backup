"""Manuel yedekleme — alan seçimi ve iptal."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from kurum_yedekleme.core.progress import BackupProgressEvent
from kurum_yedekleme.db.models import BackupArea
from kurum_yedekleme.ui.widgets.progress_panel import ProgressPanel


class BackupPage(QWidget):
    backup_requested = Signal(list)  # list[int] area ids
    cancel_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        title = QLabel("Yedekleme")
        title.setObjectName("PageTitle")
        layout.addWidget(title)
        info = QLabel(
            "Manuel yedekleme bu pencerede çalışır. "
            "Otomatik yedekleme Windows Service tarafından yapılır. "
            "Kaynak dosyalar yalnızca okunur."
        )
        info.setObjectName("Muted")
        info.setWordWrap(True)
        layout.addWidget(info)

        self._checks: list[QCheckBox] = []
        self._box = QVBoxLayout()
        layout.addLayout(self._box)

        row = QHBoxLayout()
        self.select_all_btn = QPushButton("Tam Yedekleme")
        self.select_all_btn.setObjectName("SecondaryButton")
        self.select_all_btn.clicked.connect(self._select_all_enabled)
        self.backup_btn = QPushButton("Seçili Alanları Yedekle")
        self.backup_btn.setObjectName("PrimaryButton")
        self.backup_btn.clicked.connect(self._emit_backup)
        self.cancel_btn = QPushButton("Yedeklemeyi İptal Et")
        self.cancel_btn.setObjectName("DangerButton")
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.clicked.connect(self.cancel_requested.emit)
        row.addWidget(self.select_all_btn)
        row.addWidget(self.backup_btn)
        row.addWidget(self.cancel_btn)
        row.addStretch(1)
        layout.addLayout(row)

        self.progress = ProgressPanel()
        layout.addWidget(self.progress)
        layout.addStretch(1)

    def set_areas(self, areas: list[BackupArea]) -> None:
        while self._checks:
            box = self._checks.pop()
            self._box.removeWidget(box)
            box.deleteLater()
        for area in areas:
            box = QCheckBox(f"{area.name}  —  {area.source_path}")
            box.setProperty("area_id", area.id)
            box.setEnabled(area.enabled)
            box.setChecked(area.enabled)
            if not area.enabled:
                box.setText(box.text() + " [pasif]")
            self._box.addWidget(box)
            self._checks.append(box)

    def _select_all_enabled(self) -> None:
        for box in self._checks:
            if box.isEnabled():
                box.setChecked(True)

    def _emit_backup(self) -> None:
        ids: list[int] = []
        for box in self._checks:
            if box.isChecked() and box.isEnabled():
                area_id = box.property("area_id")
                if area_id is not None:
                    ids.append(int(area_id))
        self.backup_requested.emit(ids)

    def set_busy(self, busy: bool) -> None:
        self.backup_btn.setEnabled(not busy)
        self.select_all_btn.setEnabled(not busy)
        self.cancel_btn.setEnabled(busy)
        for box in self._checks:
            box.setEnabled(not busy and "[pasif]" not in box.text())

    def apply_progress(self, event: BackupProgressEvent) -> None:
        self.progress.apply_event(event)
