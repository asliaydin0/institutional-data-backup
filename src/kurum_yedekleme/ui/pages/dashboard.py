"""Dashboard — ana ekran."""

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

from kurum_yedekleme.config.schema import AppSettings
from kurum_yedekleme.core.progress import BackupProgressEvent
from kurum_yedekleme.db.models import BackupHistoryRecord
from kurum_yedekleme.ui.widgets.info_card import InfoCard
from kurum_yedekleme.ui.widgets.progress_panel import ProgressPanel
from kurum_yedekleme.utils.formatting import format_bytes


def _duration_text(record: BackupHistoryRecord) -> str:
    if record.backup_end_time is None:
        return "—"
    delta = record.backup_end_time - record.backup_start_time
    secs = int(max(0, delta.total_seconds()))
    mins, rem = divmod(secs, 60)
    if mins:
        return f"{mins} dk {rem} sn"
    return f"{rem} sn"


class DashboardPage(QWidget):
    """Kurumsal gösterge paneli."""

    backup_requested = Signal()
    preflight_requested = Signal()
    server_test_requested = Signal()

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
        header.setSpacing(10)
        title = QLabel("Dashboard")
        title.setObjectName("PageTitle")
        header.addWidget(title)
        header.addStretch(1)
        self.preflight_btn = QPushButton("Yapılandırmayı Test Et")
        self.preflight_btn.setObjectName("SecondaryButton")
        self.preflight_btn.setToolTip(
            "Kaynak/hedef erişimi, yazma izni, disk ve config kontrolü "
            "(ZIP oluşturmaz)."
        )
        self.preflight_btn.clicked.connect(self.preflight_requested.emit)
        self.server_btn = QPushButton("Sunucu Bağlantısını Test Et")
        self.server_btn.setObjectName("SecondaryButton")
        self.server_btn.setToolTip(
            "Hedefte küçük test dosyası yazıp siler; gerçek yedek almaz."
        )
        self.server_btn.clicked.connect(self.server_test_requested.emit)
        self.backup_btn = QPushButton("Şimdi Yedekle")
        self.backup_btn.setObjectName("PrimaryButton")
        self.backup_btn.clicked.connect(self.backup_requested.emit)
        header.addWidget(self.preflight_btn)
        header.addWidget(self.server_btn)
        header.addWidget(self.backup_btn)
        root.addLayout(header)

        grid = QGridLayout()
        grid.setSpacing(12)
        self.card_system = InfoCard("Sistem durumu", "Aktif")
        self.card_last_ok = InfoCard("Son başarılı yedekleme", "—")
        self.card_next = InfoCard("Sonraki otomatik yedekleme", "—")
        self.card_source = InfoCard("Kaynak klasör", "—")
        self.card_dest = InfoCard("Sunucu hedefi", "—")
        self.card_last_status = InfoCard("Son yedekleme durumu", "—")
        cards = [
            self.card_system,
            self.card_last_ok,
            self.card_next,
            self.card_source,
            self.card_dest,
            self.card_last_status,
        ]
        for index, card in enumerate(cards):
            grid.addWidget(card, index // 3, index % 3)
        root.addLayout(grid)

        self.progress = ProgressPanel()
        root.addWidget(self.progress)

        hist_title = QLabel("Yedekleme geçmişinden son kayıtlar")
        hist_title.setObjectName("CardTitle")
        root.addWidget(hist_title)
        self.history_table = QTableWidget(0, 5)
        self.history_table.setHorizontalHeaderLabels(
            ["ID", "Tarih", "Durum", "Dosya", "ZIP"]
        )
        self.history_table.setAlternatingRowColors(True)
        self.history_table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.history_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.history_table.verticalHeader().setVisible(False)
        header_view = self.history_table.horizontalHeader()
        header_view.setStretchLastSection(False)
        header_view.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header_view.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header_view.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header_view.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header_view.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.history_table.setMaximumHeight(220)
        root.addWidget(self.history_table)
        root.addStretch(1)

        self.status_card = self.card_system

    def set_test_mode(self, active: bool) -> None:
        self._test_banner.setVisible(bool(active))

    def set_busy(self, busy: bool) -> None:
        self.backup_btn.setEnabled(not busy)
        self.preflight_btn.setEnabled(not busy)
        self.server_btn.setEnabled(not busy)

    def apply_progress(self, event: BackupProgressEvent) -> None:
        self.progress.apply_event(event)

    def refresh(
        self,
        *,
        settings: AppSettings,
        system_active: bool,
        last_success: Optional[BackupHistoryRecord],
        last_any: Optional[BackupHistoryRecord],
        recent: list[BackupHistoryRecord],
        next_run: Optional[datetime],
    ) -> None:
        self.card_system.set_value("Aktif" if system_active else "Pasif")

        if last_success is None:
            self.card_last_ok.set_value("Henüz başarılı yedek yok")
        else:
            local = last_success.backup_start_time.astimezone()
            self.card_last_ok.set_value(
                f"{local.strftime('%d.%m.%Y')}  {local.strftime('%H:%M:%S')}\n"
                f"Boyut: {format_bytes(last_success.compressed_size)}\n"
                f"Süre: {_duration_text(last_success)}"
            )

        if next_run is None:
            self.card_next.set_value("Zamanlama kapalı")
        else:
            self.card_next.set_value(next_run.strftime("%d.%m.%Y %H:%M"))

        enabled_sources = [s for s in settings.sources if s.enabled]
        if not enabled_sources:
            self.card_source.set_value("Tanımlı değil")
        elif len(enabled_sources) == 1:
            self.card_source.set_value(enabled_sources[0].path)
        else:
            self.card_source.set_value(
                f"{enabled_sources[0].path}\n(+{len(enabled_sources) - 1} kaynak daha)"
            )

        self.card_dest.set_value(settings.destination.unc_path)

        if last_any is None:
            self.card_last_status.set_value("Kayıt yok")
        else:
            msg = last_any.status.value
            if last_any.error_message:
                msg = f"{msg}\n{last_any.error_message}"
            self.card_last_status.set_value(msg)

        self.history_table.setRowCount(len(recent))
        for row, record in enumerate(recent):
            local = record.backup_start_time.astimezone()
            values = [
                str(record.id or ""),
                local.strftime("%d.%m.%Y %H:%M"),
                record.status.value,
                str(record.file_count),
                format_bytes(record.compressed_size),
            ]
            for col, value in enumerate(values):
                self.history_table.setItem(row, col, QTableWidgetItem(value))
