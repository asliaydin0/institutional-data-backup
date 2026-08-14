"""Dashboard — servis ve günlük yedek özeti."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from kurum_yedekleme.core.progress import BackupProgressEvent
from kurum_yedekleme.db.models import BackupHistoryRecord, BackupStatus
from kurum_yedekleme.services.windows_service import ServiceStatus
from kurum_yedekleme.ui.widgets.info_card import InfoCard
from kurum_yedekleme.ui.widgets.progress_panel import ProgressPanel
from kurum_yedekleme.utils.formatting import format_bytes


class DashboardPage(QWidget):
    backup_requested = Signal()
    preflight_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(14)

        self._test_banner = QLabel("⚠ TEST MODU AKTİF")
        self._test_banner.setObjectName("TestModeBanner")
        self._test_banner.setVisible(False)
        root.addWidget(self._test_banner)

        header = QHBoxLayout()
        title = QLabel("Dashboard")
        title.setObjectName("PageTitle")
        header.addWidget(title)
        header.addStretch(1)
        self.preflight_btn = QPushButton("Yapılandırmayı Test Et")
        self.preflight_btn.setObjectName("SecondaryButton")
        self.preflight_btn.clicked.connect(self.preflight_requested.emit)
        self.backup_btn = QPushButton("Şimdi Yedekle")
        self.backup_btn.setObjectName("PrimaryButton")
        self.backup_btn.clicked.connect(self.backup_requested.emit)
        header.addWidget(self.preflight_btn)
        header.addWidget(self.backup_btn)
        root.addLayout(header)

        grid = QGridLayout()
        grid.setSpacing(12)
        self.card_service = InfoCard("Windows Service", "—")
        self.card_auto = InfoCard("Otomatik yedekleme", "—")
        self.card_today = InfoCard("Bugünkü yedek", "—")
        self.card_last_auto = InfoCard("Son otomatik yedek", "—")
        self.card_last_manual = InfoCard("Son manuel yedek", "—")
        self.card_areas = InfoCard("Aktif alanlar", "—")
        self.card_last_area = InfoCard("Son yedeklenen alan", "—")
        self.card_error = InfoCard("Son hata", "—")
        cards = [
            self.card_service,
            self.card_auto,
            self.card_today,
            self.card_last_auto,
            self.card_last_manual,
            self.card_areas,
            self.card_last_area,
            self.card_error,
        ]
        for index, card in enumerate(cards):
            grid.addWidget(card, index // 4, index % 4)
        root.addLayout(grid)

        self.progress = ProgressPanel()
        root.addWidget(self.progress)

        hist_title = QLabel("Son kayıtlar")
        hist_title.setObjectName("CardTitle")
        root.addWidget(hist_title)
        self.history_table = QTableWidget(0, 5)
        self.history_table.setHorizontalHeaderLabels(
            ["Tarih", "Alan", "Tür", "Durum", "Boyut"]
        )
        self.history_table.setAlternatingRowColors(True)
        self.history_table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.history_table.verticalHeader().setVisible(False)
        header_view = self.history_table.horizontalHeader()
        header_view.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header_view.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.history_table.setMaximumHeight(220)
        root.addWidget(self.history_table)
        root.addStretch(1)

        self.status_card = self.card_service
        self._test_mode = False

    def set_test_mode(self, active: bool) -> None:
        self._test_mode = bool(active)
        self._test_banner.setVisible(self._test_mode)

    def set_busy(self, busy: bool) -> None:
        self.backup_btn.setEnabled(not busy)
        self.preflight_btn.setEnabled(not busy)

    def apply_progress(self, event: BackupProgressEvent) -> None:
        self.progress.apply_event(event)

    def refresh(
        self,
        *,
        service: ServiceStatus,
        schedule_enabled: bool,
        schedule_time: str,
        next_run: Optional[datetime],
        missed: bool,
        active_areas: int,
        today_success: int,
        today_failed: int,
        last_auto: Optional[BackupHistoryRecord],
        last_manual: Optional[BackupHistoryRecord],
        last_any: Optional[BackupHistoryRecord],
        last_error: Optional[BackupHistoryRecord],
        recent: list[BackupHistoryRecord],
    ) -> None:
        self.card_service.set_value(service.label_tr)
        auto_text = f"{'Açık' if schedule_enabled else 'Kapalı'} @ {schedule_time}"
        if next_run is not None:
            auto_text += f"\nSonraki: {next_run.strftime('%d.%m.%Y %H:%M')}"
        if missed:
            auto_text += "\nBugünün otomatik yedeklemesi henüz yapılmadı."
        if service.state != "running" and schedule_enabled:
            if self._test_mode:
                auto_text += (
                    "\nTEST MODU — otomatik yedek bu pencere açıkken çalışır."
                )
            else:
                auto_text += "\nServis kapalı — otomatik yedek çalışmaz."
        self.card_auto.set_value(auto_text)

        total_today = today_success + today_failed
        if total_today == 0:
            self.card_today.set_value("Kayıt yok")
        else:
            self.card_today.set_value(
                f"{today_success} / {total_today} başarılı"
                + (f"\n{today_failed} başarısız" if today_failed else "")
            )
        self.card_areas.set_value(str(active_areas))
        self.card_last_auto.set_value(_record_summary(last_auto))
        self.card_last_manual.set_value(_record_summary(last_manual))
        if last_any is None:
            self.card_last_area.set_value("—")
        else:
            self.card_last_area.set_value(last_any.area_name)
        if last_error is None:
            self.card_error.set_value("Yok")
        else:
            self.card_error.set_value(
                f"{last_error.area_name}\n{(last_error.error_message or '')[:80]}"
            )

        self.history_table.setRowCount(0)
        for record in recent[:8]:
            row = self.history_table.rowCount()
            self.history_table.insertRow(row)
            local = record.started_at.astimezone()
            self.history_table.setItem(
                row, 0, QTableWidgetItem(local.strftime("%d.%m.%Y %H:%M"))
            )
            self.history_table.setItem(row, 1, QTableWidgetItem(record.area_name))
            self.history_table.setItem(
                row, 2, QTableWidgetItem(record.backup_type.label_tr)
            )
            self.history_table.setItem(
                row, 3, QTableWidgetItem(record.status.label_tr)
            )
            self.history_table.setItem(
                row, 4, QTableWidgetItem(format_bytes(record.file_size))
            )


def _record_summary(record: Optional[BackupHistoryRecord]) -> str:
    if record is None:
        return "—"
    local = record.started_at.astimezone()
    return (
        f"{local.strftime('%d.%m.%Y %H:%M')}\n"
        f"{record.area_name} — {record.status.label_tr}"
    )
