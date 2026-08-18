"""Ayarlar — zamanlama, E:\\Yedekler, saklama, Windows Service."""

from __future__ import annotations

from dataclasses import replace

from PySide6.QtCore import QTime, Signal
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QCheckBox,
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTimeEdit,
    QVBoxLayout,
    QWidget,
)

from kurum_yedekleme.config.loader import ConfigError
from kurum_yedekleme.config.retention_schema import WEEKDAY_LABELS_TR
from kurum_yedekleme.config.schema import AppSettings
from kurum_yedekleme.config.writer import save_runtime_settings, validate_schedule_time
from kurum_yedekleme.services.windows_service import (
    ServiceStatus,
    query_service,
    start_service,
    stop_service,
)


class SettingsPage(QWidget):
    settings_saved = Signal(object)

    def __init__(
        self,
        settings: AppSettings,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._settings = settings
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)

        title = QLabel("Ayarlar")
        title.setObjectName("PageTitle")
        layout.addWidget(title)

        form = QFormLayout()
        self._root = QLineEdit(settings.backup_root)
        self._root.setReadOnly(True)
        self._root.setToolTip("Production yedekleri yalnızca E:\\Yedekler altındadır.")
        form.addRow("Yedek kökü:", self._root)

        self._enabled = QCheckBox("Otomatik yedeklemeyi etkinleştir")
        self._enabled.setChecked(settings.schedule.enabled)
        self._enabled.toggled.connect(self._sync_schedule_fields)
        form.addRow(self._enabled)

        self._schedule_freq = QComboBox()
        self._schedule_freq.addItem("Günlük", "daily")
        self._schedule_freq.addItem("Haftalık", "weekly")
        self._schedule_freq.addItem("Aylık", "monthly")
        sidx = self._schedule_freq.findData(settings.schedule.frequency)
        self._schedule_freq.setCurrentIndex(sidx if sidx >= 0 else 0)
        self._schedule_freq.currentIndexChanged.connect(self._sync_schedule_fields)
        form.addRow("Yedekleme sıklığı:", self._schedule_freq)

        self._time_edit = QTimeEdit()
        self._time_edit.setDisplayFormat("HH:mm")
        self._time_edit.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.UpDownArrows)
        hour, minute = self._parse_time(settings.schedule.time)
        self._time_edit.setTime(QTime(hour, minute))
        form.addRow("Yedekleme saati:", self._time_edit)

        self._schedule_weekday = QComboBox()
        for day_index, label in enumerate(WEEKDAY_LABELS_TR):
            self._schedule_weekday.addItem(label, day_index)
        swidx = self._schedule_weekday.findData(settings.schedule.weekday)
        self._schedule_weekday.setCurrentIndex(swidx if swidx >= 0 else 6)
        form.addRow("Yedekleme günü:", self._schedule_weekday)

        self._schedule_dom = QSpinBox()
        self._schedule_dom.setRange(1, 28)
        self._schedule_dom.setValue(settings.schedule.day_of_month)
        form.addRow("Ayın günü:", self._schedule_dom)

        self._retention_enabled = QCheckBox("Eski yedekleri otomatik sil")
        self._retention_enabled.setChecked(settings.retention.enabled)
        self._retention_enabled.toggled.connect(self._sync_retention_fields)
        form.addRow(self._retention_enabled)

        self._retention_keep = QSpinBox()
        self._retention_keep.setRange(1, 3650)
        self._retention_keep.setSuffix(" gün")
        self._retention_keep.setValue(settings.retention.keep_days)
        self._retention_keep.setToolTip(
            "Bu süreden daha eski tarih klasörlerindeki ZIP dosyaları silinir."
        )
        form.addRow("Saklama süresi:", self._retention_keep)

        self._retention_freq = QComboBox()
        self._retention_freq.addItem("Günlük", "daily")
        self._retention_freq.addItem("Haftalık", "weekly")
        self._retention_freq.addItem("Aylık", "monthly")
        idx = self._retention_freq.findData(settings.retention.frequency)
        self._retention_freq.setCurrentIndex(idx if idx >= 0 else 1)
        self._retention_freq.currentIndexChanged.connect(self._sync_retention_fields)
        form.addRow("Temizlik sıklığı:", self._retention_freq)

        self._retention_time = QTimeEdit()
        self._retention_time.setDisplayFormat("HH:mm")
        self._retention_time.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.UpDownArrows)
        rh, rm = self._parse_time(settings.retention.time)
        self._retention_time.setTime(QTime(rh, rm))
        form.addRow("Temizlik saati:", self._retention_time)

        self._retention_weekday = QComboBox()
        for day_index, label in enumerate(WEEKDAY_LABELS_TR):
            self._retention_weekday.addItem(label, day_index)
        widx = self._retention_weekday.findData(settings.retention.weekday)
        self._retention_weekday.setCurrentIndex(widx if widx >= 0 else 6)
        form.addRow("Temizlik günü:", self._retention_weekday)

        self._retention_dom = QSpinBox()
        self._retention_dom.setRange(1, 28)
        self._retention_dom.setValue(settings.retention.day_of_month)
        form.addRow("Ayın günü:", self._retention_dom)

        self._form = form
        layout.addLayout(form)
        self._sync_schedule_fields()
        self._sync_retention_fields()

        self._hint = QLabel(
            "Otomatik yedekleme ve eski ZIP temizliği Windows Service tarafından "
            "çalıştırılır. GUI kapatılsa bile servis devam eder. "
            "Alanlar SQLite'da tutulur."
        )
        self._hint.setObjectName("Muted")
        self._hint.setWordWrap(True)
        layout.addWidget(self._hint)

        self._svc_label = QLabel("Servis: —")
        layout.addWidget(self._svc_label)
        svc_row = QHBoxLayout()
        self._svc_install = QPushButton("Servisi Kur")
        self._svc_start = QPushButton("Servisi Başlat")
        self._svc_stop = QPushButton("Servisi Durdur")
        self._svc_remove = QPushButton("Servisi Kaldır")
        for btn in (
            self._svc_install,
            self._svc_start,
            self._svc_stop,
            self._svc_remove,
        ):
            btn.setObjectName("SecondaryButton")
            svc_row.addWidget(btn)
        svc_row.addStretch(1)
        layout.addLayout(svc_row)
        self._svc_install.clicked.connect(self._install_service)
        self._svc_start.clicked.connect(self._start_service)
        self._svc_stop.clicked.connect(self._stop_service)
        self._svc_remove.clicked.connect(self._remove_service)

        self._save_btn = QPushButton("Ayarları Kaydet")
        self._save_btn.setObjectName("PrimaryButton")
        self._save_btn.clicked.connect(self._on_save)
        layout.addWidget(self._save_btn)
        layout.addStretch(1)
        self._test_mode = False
        self.refresh_service_status()

    def set_test_mode(self, active: bool) -> None:
        self._test_mode = bool(active)
        for btn in (
            self._svc_install,
            self._svc_start,
            self._svc_stop,
            self._svc_remove,
        ):
            btn.setEnabled(not self._test_mode)
        if self._test_mode:
            self._root.setReadOnly(False)
            self._hint.setText(
                "⚠ TEST MODU — yedek kökü test klasörüdür. "
                "Servis kurulumu ve config.yaml yazılmaz; oturuma uygulanır. "
                "Otomatik yedek bu pencere açıkken, ayarlanan saatte çalışır; "
                "saat geçmişse kaçırılmış yedek hemen alınır."
            )
            self._save_btn.setText("Oturuma Uygula")
        else:
            self._root.setReadOnly(True)
            self._save_btn.setText("Ayarları Kaydet")

    def apply_settings(self, settings: AppSettings) -> None:
        self._settings = settings
        self._root.setText(settings.backup_root)
        self._enabled.setChecked(settings.schedule.enabled)
        hour, minute = self._parse_time(settings.schedule.time)
        self._time_edit.setTime(QTime(hour, minute))
        sidx = self._schedule_freq.findData(settings.schedule.frequency)
        if sidx >= 0:
            self._schedule_freq.setCurrentIndex(sidx)
        swidx = self._schedule_weekday.findData(settings.schedule.weekday)
        if swidx >= 0:
            self._schedule_weekday.setCurrentIndex(swidx)
        self._schedule_dom.setValue(settings.schedule.day_of_month)
        self._sync_schedule_fields()
        self._retention_enabled.setChecked(settings.retention.enabled)
        self._retention_keep.setValue(settings.retention.keep_days)
        idx = self._retention_freq.findData(settings.retention.frequency)
        if idx >= 0:
            self._retention_freq.setCurrentIndex(idx)
        rh, rm = self._parse_time(settings.retention.time)
        self._retention_time.setTime(QTime(rh, rm))
        widx = self._retention_weekday.findData(settings.retention.weekday)
        if widx >= 0:
            self._retention_weekday.setCurrentIndex(widx)
        self._retention_dom.setValue(settings.retention.day_of_month)
        self._sync_retention_fields()

    def _sync_schedule_fields(self) -> None:
        enabled = self._enabled.isChecked()
        freq = self._schedule_freq.currentData()
        for widget in (
            self._schedule_freq,
            self._time_edit,
            self._schedule_weekday,
            self._schedule_dom,
        ):
            widget.setEnabled(enabled)
        weekly = enabled and freq == "weekly"
        monthly = enabled and freq == "monthly"
        self._schedule_weekday.setVisible(weekly)
        self._schedule_dom.setVisible(monthly)
        label_week = self._form.labelForField(self._schedule_weekday)
        if label_week is not None:
            label_week.setVisible(weekly)
        label_dom = self._form.labelForField(self._schedule_dom)
        if label_dom is not None:
            label_dom.setVisible(monthly)

    def _schedule_values(self) -> tuple[bool, str, str, int, int]:
        qtime = self._time_edit.time()
        time_str = f"{qtime.hour():02d}:{qtime.minute():02d}"
        return (
            self._enabled.isChecked(),
            str(self._schedule_freq.currentData()),
            time_str,
            int(self._schedule_weekday.currentData()),
            self._schedule_dom.value(),
        )

    def _sync_retention_fields(self) -> None:
        enabled = self._retention_enabled.isChecked()
        freq = self._retention_freq.currentData()
        for widget in (
            self._retention_keep,
            self._retention_freq,
            self._retention_time,
            self._retention_weekday,
            self._retention_dom,
        ):
            widget.setEnabled(enabled)
        weekly = enabled and freq == "weekly"
        monthly = enabled and freq == "monthly"
        self._retention_weekday.setVisible(weekly)
        self._retention_dom.setVisible(monthly)
        label_week = self._form.labelForField(self._retention_weekday)
        if label_week is not None:
            label_week.setVisible(weekly)
        label_dom = self._form.labelForField(self._retention_dom)
        if label_dom is not None:
            label_dom.setVisible(monthly)

    def _retention_values(self) -> tuple[bool, int, str, str, int, int]:
        qtime = self._retention_time.time()
        time_str = f"{qtime.hour():02d}:{qtime.minute():02d}"
        return (
            self._retention_enabled.isChecked(),
            self._retention_keep.value(),
            str(self._retention_freq.currentData()),
            time_str,
            int(self._retention_weekday.currentData()),
            self._retention_dom.value(),
        )

    def refresh_service_status(self, status: ServiceStatus | None = None) -> None:
        current = status or query_service()
        self._svc_label.setText(f"Servis: {current.label_tr}")

    def _on_save(self) -> None:
        (
            sched_enabled,
            sched_freq,
            sched_time,
            sched_weekday,
            sched_dom,
        ) = self._schedule_values()
        (
            ret_enabled,
            ret_keep,
            ret_freq,
            ret_time,
            ret_weekday,
            ret_dom,
        ) = self._retention_values()
        try:
            validate_schedule_time(sched_time)
            validate_schedule_time(ret_time)
            if self._test_mode:
                from kurum_yedekleme.config.writer import (
                    validate_retention_settings,
                    validate_schedule_settings,
                )

                updated = replace(
                    self._settings,
                    backup_root=self._root.text().strip() or self._settings.backup_root,
                    schedule=validate_schedule_settings(
                        replace(
                            self._settings.schedule,
                            enabled=sched_enabled,
                            frequency=sched_freq,
                            time=sched_time,
                            weekday=sched_weekday,
                            day_of_month=sched_dom,
                        )
                    ),
                    retention=validate_retention_settings(
                        replace(
                            self._settings.retention,
                            enabled=ret_enabled,
                            keep_days=ret_keep,
                            frequency=ret_freq,
                            time=ret_time,
                            weekday=ret_weekday,
                            day_of_month=ret_dom,
                        )
                    ),
                )
            else:
                updated = save_runtime_settings(
                    backup_root=self._settings.backup_root,
                    schedule_enabled=sched_enabled,
                    schedule_frequency=sched_freq,
                    schedule_time=sched_time,
                    schedule_weekday=sched_weekday,
                    schedule_day_of_month=sched_dom,
                    retention_enabled=ret_enabled,
                    retention_keep_days=ret_keep,
                    retention_frequency=ret_freq,
                    retention_time=ret_time,
                    retention_weekday=ret_weekday,
                    retention_day_of_month=ret_dom,
                )
        except ConfigError as exc:
            QMessageBox.warning(self, "Ayarlar", str(exc))
            return
        self.apply_settings(updated)
        self.settings_saved.emit(updated)
        QMessageBox.information(
            self,
            "Ayarlar",
            "Ayarlar kaydedildi."
            if not self._test_mode
            else (
                "Ayarlar bu TEST MODE oturumuna uygulandı.\n\n"
                "Otomatik yedekleme açıksa bu pencere kapanmadan çalışır. "
                "Saat bugün geçmişse kaçırılmış yedek şimdi alınır."
            ),
        )

    def _install_service(self) -> None:
        try:
            from kurum_yedekleme.win_service import install_win32_service

            install_win32_service()
            QMessageBox.information(self, "Servis", "Windows Service kuruldu.")
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(
                self,
                "Servis",
                "Servis kurulamadı (yönetici yetkisi ve pywin32 gerekir).\n\n"
                f"{exc}",
            )
        self.refresh_service_status()

    def _remove_service(self) -> None:
        try:
            from kurum_yedekleme.win_service import remove_win32_service

            remove_win32_service()
            QMessageBox.information(self, "Servis", "Windows Service kaldırıldı.")
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Servis", str(exc))
        self.refresh_service_status()

    def _start_service(self) -> None:
        try:
            start_service()
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Servis", str(exc))
        self.refresh_service_status()

    def _stop_service(self) -> None:
        try:
            stop_service()
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Servis", str(exc))
        self.refresh_service_status()

    @staticmethod
    def _parse_time(value: str) -> tuple[int, int]:
        try:
            hour_s, minute_s = value.split(":")
            return int(hour_s), int(minute_s)
        except (ValueError, AttributeError):
            return 2, 0
