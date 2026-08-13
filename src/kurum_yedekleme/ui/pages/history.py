"""Yedekleme geçmişi sayfası."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from kurum_yedekleme.services.history_service import HistoryService
from kurum_yedekleme.utils.formatting import format_bytes


class HistoryPage(QWidget):
    """Geçmiş listesi — yalnızca HistoryService."""

    def __init__(
        self,
        history_service: HistoryService | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._history = history_service

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)

        heading = QLabel("Geçmiş")
        heading.setObjectName("PageTitle")
        layout.addWidget(heading)

        summary = QHBoxLayout()
        self._lbl_total = QLabel("Toplam: -")
        self._lbl_success = QLabel("Başarılı: -")
        self._lbl_failed = QLabel("Başarısız: -")
        summary.addWidget(self._lbl_total)
        summary.addWidget(self._lbl_success)
        summary.addWidget(self._lbl_failed)
        summary.addStretch(1)
        layout.addLayout(summary)

        self._table = QTableWidget(0, 8)
        self._table.setHorizontalHeaderLabels(
            [
                "ID",
                "Başlangıç",
                "Bitiş",
                "Durum",
                "Dosya",
                "Orijinal",
                "ZIP",
                "Hedef",
            ]
        )
        self._table.setAlternatingRowColors(True)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self._table.verticalHeader().setVisible(False)
        header = self._table.horizontalHeader()
        header.setStretchLastSection(True)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(7, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self._table)
        self.refresh()

    def refresh(self) -> None:
        if self._history is None:
            self._table.setRowCount(0)
            return
        total = self._history.count_all()
        success = self._history.count_successful()
        failed = len(self._history.get_failed_backups())
        rows = self._history.get_last_n(50)
        self._lbl_total.setText(f"Toplam: {total}")
        self._lbl_success.setText(f"Başarılı: {success}")
        self._lbl_failed.setText(f"Başarısız: {failed}")
        self._table.setRowCount(len(rows))
        for index, record in enumerate(rows):
            start = record.backup_start_time.astimezone().strftime("%d.%m.%Y %H:%M:%S")
            end = (
                record.backup_end_time.astimezone().strftime("%d.%m.%Y %H:%M:%S")
                if record.backup_end_time
                else "—"
            )
            values = [
                str(record.id or ""),
                start,
                end,
                record.status.value,
                str(record.file_count),
                format_bytes(record.original_size),
                format_bytes(record.compressed_size),
                record.destination_path or "—",
            ]
            for col, value in enumerate(values):
                self._table.setItem(index, col, QTableWidgetItem(value))
