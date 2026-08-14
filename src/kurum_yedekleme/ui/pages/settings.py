"""Ayarlar — zamanlama, E:\\Yedekler, retry, Windows Service."""

from __future__ import annotations

from dataclasses import replace

from PySide6.QtCore import QTime, Signal
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QCheckBox,
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

        self._enabled = QCheckBox("Günlük otomatik yedeklemeyi etkinleştir")
        self._enabled.setChecked(settings.schedule.enabled)
        form.addRow(self._enabled)

        self._time_edit = QTimeEdit()
        self._time_edit.setDisplayFormat("HH:mm")
        self._time_edit.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.UpDownArrows)
        hour, minute = self._parse_time(settings.schedule.time)
        self._time_edit.setTime(QTime(hour, minute))
        form.addRow("Yedekleme saati:", self._time_edit)

        self._retry_count = QSpinBox()
        self._retry_count.setRange(1, 20)
        self._retry_count.setValue(settings.retry.max_attempts)
        form.addRow("Retry sayısı:", self._retry_count)

        self._retry_delay = QSpinBox()
        self._retry_delay.setRange(0, 3600)
        self._retry_delay.setSuffix(" sn")
        self._retry_delay.setValue(settings.retry.initial_delay_seconds)
        form.addRow("Retry bekleme:", self._retry_delay)

        self._zip_level = QSpinBox()
        self._zip_level.setRange(0, 9)
        self._zip_level.setValue(settings.zip.compresslevel)
        form.addRow("ZIP sıkıştırma:", self._zip_level)
        layout.addLayout(form)

        self._hint = QLabel(
            "Otomatik yedekleme Windows Service tarafından çalıştırılır. "
            "GUI kapatılsa bile servis devam eder. Alanlar SQLite'da tutulur."
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
        self._retry_count.setValue(settings.retry.max_attempts)
        self._retry_delay.setValue(settings.retry.initial_delay_seconds)
        self._zip_level.setValue(settings.zip.compresslevel)

    def refresh_service_status(self, status: ServiceStatus | None = None) -> None:
        current = status or query_service()
        self._svc_label.setText(f"Servis: {current.label_tr}")

    def _on_save(self) -> None:
        qtime = self._time_edit.time()
        time_str = f"{qtime.hour():02d}:{qtime.minute():02d}"
        try:
            validate_schedule_time(time_str)
            if self._test_mode:
                updated = replace(
                    self._settings,
                    backup_root=self._root.text().strip() or self._settings.backup_root,
                    schedule=replace(
                        self._settings.schedule,
                        enabled=self._enabled.isChecked(),
                        time=time_str,
                    ),
                    retry=replace(
                        self._settings.retry,
                        max_attempts=self._retry_count.value(),
                        initial_delay_seconds=self._retry_delay.value(),
                    ),
                    zip=replace(
                        self._settings.zip,
                        compresslevel=self._zip_level.value(),
                    ),
                )
            else:
                updated = save_runtime_settings(
                    backup_root=self._settings.backup_root,
                    schedule_enabled=self._enabled.isChecked(),
                    schedule_time=time_str,
                    retry_max_attempts=self._retry_count.value(),
                    retry_delay_seconds=self._retry_delay.value(),
                    zip_compresslevel=self._zip_level.value(),
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
