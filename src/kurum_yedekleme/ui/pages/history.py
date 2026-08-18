"""Yedekleme geçmişi — alan / tür / durum / tarih filtresi."""

from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDateEdit,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from kurum_yedekleme.db.models import BackupArea, BackupStatus, BackupType
from kurum_yedekleme.services.history_service import HistoryService
from kurum_yedekleme.utils.formatting import format_bytes
from kurum_yedekleme.utils.windows_paths import reveal_in_file_manager


def _duration_text(seconds: float | None) -> str:
    if seconds is None:
        return "—"
    total = int(max(0, seconds))
    mins, rem = divmod(total, 60)
    if mins:
        return f"{mins} dk {rem} sn"
    return f"{rem} sn"


class HistoryPage(QWidget):
    def __init__(
        self,
        history_service: HistoryService | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._history = history_service
        self._areas: list[BackupArea] = []

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

        filters = QHBoxLayout()
        self._area_combo = QComboBox()
        self._type_combo = QComboBox()
        self._type_combo.addItems(["Tümü", "Manuel", "Otomatik"])
        self._status_combo = QComboBox()
        self._status_combo.addItems(["Tümü", "Başarılı", "Başarısız", "İptal"])
        self._from = QDateEdit()
        self._from.setCalendarPopup(True)
        self._from.setDate(QDate.currentDate().addMonths(-1))
        self._to = QDateEdit()
        self._to.setCalendarPopup(True)
        self._to.setDate(QDate.currentDate())
        apply_btn = QPushButton("Filtrele")
        apply_btn.setObjectName("SecondaryButton")
        apply_btn.clicked.connect(self.refresh)
        filters.addWidget(QLabel("Alan:"))
        filters.addWidget(self._area_combo)
        filters.addWidget(QLabel("Tür:"))
        filters.addWidget(self._type_combo)
        filters.addWidget(QLabel("Durum:"))
        filters.addWidget(self._status_combo)
        filters.addWidget(QLabel("Başlangıç:"))
        filters.addWidget(self._from)
        filters.addWidget(QLabel("Bitiş:"))
        filters.addWidget(self._to)
        filters.addWidget(apply_btn)
        layout.addLayout(filters)

        self._table = QTableWidget(0, 6)
        self._table.setHorizontalHeaderLabels(
            ["Tarih", "Alan", "Tür", "Boyut", "Süre", "Durum"]
        )
        self._table.setAlternatingRowColors(True)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.verticalHeader().setVisible(False)
        self._table.setToolTip(
            "Yedek dosyasının klasörünü açmak için bir satıra çift tıklayın."
        )
        self._table.cellDoubleClicked.connect(self._on_row_activated)
        header = self._table.horizontalHeader()
        header.setStretchLastSection(True)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self._table)
        self.refresh()

    def set_areas(self, areas: list[BackupArea]) -> None:
        current = self._area_combo.currentText()
        self._areas = list(areas)
        self._area_combo.blockSignals(True)
        self._area_combo.clear()
        self._area_combo.addItem("Tümü", None)
        for area in areas:
            self._area_combo.addItem(area.name, area.id)
        idx = self._area_combo.findText(current)
        if idx >= 0:
            self._area_combo.setCurrentIndex(idx)
        self._area_combo.blockSignals(False)

    def refresh(self) -> None:
        if self._history is None:
            return
        area_id = self._area_combo.currentData()
        type_map = {1: BackupType.MANUAL, 2: BackupType.AUTOMATIC}
        status_map = {
            1: BackupStatus.SUCCESS,
            2: BackupStatus.FAILED,
            3: BackupStatus.CANCELLED,
        }
        backup_type = type_map.get(self._type_combo.currentIndex())
        status = status_map.get(self._status_combo.currentIndex())
        from_q = self._from.date()
        to_q = self._to.date()
        tz = datetime.now().astimezone().tzinfo
        start = datetime(
            from_q.year(), from_q.month(), from_q.day(), 0, 0, 0, tzinfo=tz
        )
        end = datetime(
            to_q.year(), to_q.month(), to_q.day(), 23, 59, 59, tzinfo=tz
        )
        rows = self._history.filter(
            area_id=area_id,
            backup_type=backup_type,
            status=status,
            start=start,
            end=end,
        )
        self._table.setRowCount(0)
        success = 0
        failed = 0
        for record in rows:
            if record.status == BackupStatus.SUCCESS:
                success += 1
            elif record.status == BackupStatus.FAILED:
                failed += 1
            row = self._table.rowCount()
            self._table.insertRow(row)
            local = record.started_at.astimezone()
            date_item = QTableWidgetItem(local.strftime("%d.%m.%Y %H:%M"))
            if record.backup_file:
                date_item.setData(Qt.ItemDataRole.UserRole, record.backup_file)
                date_item.setToolTip(record.backup_file)
            self._table.setItem(row, 0, date_item)
            self._table.setItem(row, 1, QTableWidgetItem(record.area_name))
            self._table.setItem(
                row, 2, QTableWidgetItem(record.backup_type.label_tr)
            )
            self._table.setItem(
                row, 3, QTableWidgetItem(format_bytes(record.file_size))
            )
            self._table.setItem(
                row, 4, QTableWidgetItem(_duration_text(record.duration_seconds))
            )
            self._table.setItem(row, 5, QTableWidgetItem(record.status.label_tr))
        self._lbl_total.setText(f"Toplam: {len(rows)}")
        self._lbl_success.setText(f"Başarılı: {success}")
        self._lbl_failed.setText(f"Başarısız: {failed}")

    def _on_row_activated(self, row: int, _column: int) -> None:
        item = self._table.item(row, 0)
        if item is None:
            return
        backup_file = item.data(Qt.ItemDataRole.UserRole)
        if not backup_file:
            QMessageBox.information(
                self,
                "Geçmiş",
                "Bu kayıt için yedek dosyası bulunmuyor.",
            )
            return
        try:
            reveal_in_file_manager(str(backup_file))
        except FileNotFoundError:
            QMessageBox.warning(
                self,
                "Geçmiş",
                f"Yedek dosyası bulunamadı:\n{backup_file}",
            )
        except OSError as exc:
            QMessageBox.warning(
                self,
                "Geçmiş",
                f"Klasör açılamadı:\n{exc}",
            )
