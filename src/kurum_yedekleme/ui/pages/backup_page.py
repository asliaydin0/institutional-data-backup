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
from kurum_yedekleme.ui.widgets.page_header import PageHeader
from kurum_yedekleme.ui.widgets.progress_panel import ProgressPanel
from kurum_yedekleme.ui.widgets.section_panel import SectionPanel


class BackupPage(QWidget):
    backup_requested = Signal(list)  # list[int] area ids
    cancel_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(16)

        layout.addWidget(
            PageHeader(
                "Yedekleme",
                "Manuel yedekleme bu ekrandan başlatılır. "
                "Otomatik yedekleme Windows Service tarafından yürütülür.",
            )
        )

        areas_panel = SectionPanel("Yedeklenecek Alanlar")
        self._checks: list[QCheckBox] = []
        self._box = QVBoxLayout()
        self._box.setSpacing(8)
        areas_panel.add_layout(self._box)
        layout.addWidget(areas_panel)

        row = QHBoxLayout()
        row.setSpacing(8)
        self.select_all_btn = QPushButton("Tümünü Seç")
        self.select_all_btn.setObjectName("SecondaryButton")
        self.select_all_btn.clicked.connect(self._toggle_select_all_enabled)
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
        while self._box.count():
            item = self._box.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._checks.clear()
        if not areas:
            empty = QLabel("Henüz tanımlı yedekleme alanı yok.")
            empty.setObjectName("Muted")
            self._box.addWidget(empty)
            return
        for area in areas:
            box = QCheckBox(f"{area.name}  —  {area.source_path}")
            box.setProperty("area_id", area.id)
            box.setEnabled(area.enabled)
            box.setChecked(area.enabled)
            if not area.enabled:
                box.setText(box.text() + "  [pasif]")
            self._box.addWidget(box)
            self._checks.append(box)
            box.toggled.connect(self._sync_select_all_label)
        self._sync_select_all_label()

    def _enabled_checks(self) -> list[QCheckBox]:
        return [box for box in self._checks if box.isEnabled()]

    def _all_enabled_selected(self) -> bool:
        enabled = self._enabled_checks()
        return bool(enabled) and all(box.isChecked() for box in enabled)

    def _sync_select_all_label(self) -> None:
        if self._all_enabled_selected():
            self.select_all_btn.setText("Seçimi Kaldır")
        else:
            self.select_all_btn.setText("Tümünü Seç")

    def _toggle_select_all_enabled(self) -> None:
        enabled = self._enabled_checks()
        if not enabled:
            return
        select_all = not self._all_enabled_selected()
        for box in enabled:
            box.setChecked(select_all)
        self._sync_select_all_label()

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
