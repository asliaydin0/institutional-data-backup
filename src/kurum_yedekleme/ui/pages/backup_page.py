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
    auto_backup_toggled = Signal(int, bool)  # area_id, selected

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(16)

        layout.addWidget(
            PageHeader(
                "Yedekleme",
                "İşaretli alanlar hem manuel hem otomatik yedekte alınır. "
                "Otomatik yedekleme Windows Service tarafından yürütülür.",
            )
        )

        areas_panel = SectionPanel("Yedeklenecek Alanlar")
        self._checks: list[QCheckBox] = []
        self._areas_snapshot: tuple | None = None
        self._busy = False
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
        snapshot = tuple(
            (
                area.id,
                area.name,
                area.source_path,
                area.enabled,
                area.deleted,
                area.auto_backup,
            )
            for area in areas
        )
        if snapshot == self._areas_snapshot:
            return

        selected_ids: set[int] | None = None
        if self._checks:
            selected_ids = {
                int(box.property("area_id"))
                for box in self._checks
                if box.isChecked() and box.property("area_id") is not None
            }

        while self._box.count():
            item = self._box.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._checks.clear()
        self._areas_snapshot = snapshot
        if not areas:
            empty = QLabel("Henüz tanımlı yedekleme alanı yok.")
            empty.setObjectName("Muted")
            self._box.addWidget(empty)
            self._sync_select_all_label()
            return
        for area in areas:
            box = QCheckBox(f"{area.name}  —  {area.source_path}")
            box.setProperty("area_id", area.id)
            box.setEnabled(bool(area.enabled) and not self._busy)
            box.blockSignals(True)
            if selected_ids is None:
                box.setChecked(bool(area.enabled and area.auto_backup))
            else:
                box.setChecked(bool(area.enabled and area.id in selected_ids))
            box.blockSignals(False)
            if not area.enabled:
                box.setText(box.text() + "  [pasif]")
            self._box.addWidget(box)
            self._checks.append(box)
            area_id = area.id
            box.toggled.connect(
                lambda checked, i=area_id: self._on_box_toggled(i, checked)
            )
        self._sync_select_all_label()

    def _enabled_checks(self) -> list[QCheckBox]:
        return [box for box in self._checks if box.isEnabled()]

    def _all_enabled_selected(self) -> bool:
        enabled = self._enabled_checks()
        return bool(enabled) and all(box.isChecked() for box in enabled)

    def _on_box_toggled(self, area_id: int | None, checked: bool) -> None:
        self._sync_select_all_label()
        if area_id is not None:
            self.auto_backup_toggled.emit(int(area_id), bool(checked))

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
        self._busy = busy
        self.backup_btn.setEnabled(not busy)
        self.select_all_btn.setEnabled(not busy)
        self.cancel_btn.setEnabled(busy)
        for box in self._checks:
            box.setEnabled(not busy and "[pasif]" not in box.text())

    def apply_progress(self, event: BackupProgressEvent) -> None:
        self.progress.apply_event(event)
