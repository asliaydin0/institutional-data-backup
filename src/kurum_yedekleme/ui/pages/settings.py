"""Ayarlar ekranı — kaynak, hedef, zamanlama, retry, ZIP."""

from __future__ import annotations

from dataclasses import replace

from PySide6.QtCore import QTime, Signal
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QCheckBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTimeEdit,
    QVBoxLayout,
    QWidget,
)

from kurum_yedekleme.config.loader import ConfigError
from kurum_yedekleme.config.schema import AppSettings, SourceConfig
from kurum_yedekleme.config.writer import save_runtime_settings, validate_schedule_time


class SettingsPage(QWidget):
    """Kalıcı uygulama ayarları."""

    settings_saved = Signal(object)  # AppSettings
    server_test_requested = Signal()
    # Geriye dönük alias
    schedule_saved = settings_saved

    def __init__(
        self,
        settings: AppSettings,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._settings = settings
        self._sources: list[SourceConfig] = list(settings.sources)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)

        title = QLabel("Ayarlar")
        title.setObjectName("PageTitle")
        layout.addWidget(title)

        # Kaynaklar
        layout.addWidget(QLabel("Kaynak klasörler"))
        self._source_list = QListWidget()
        self._source_list.setObjectName("SourceList")
        self._source_list.setMinimumHeight(120)
        layout.addWidget(self._source_list)
        src_btns = QHBoxLayout()
        add_btn = QPushButton("Klasör Ekle")
        add_btn.setObjectName("SecondaryButton")
        add_btn.clicked.connect(self._add_source)
        remove_btn = QPushButton("Seçileni Çıkar")
        remove_btn.setObjectName("DangerButton")
        remove_btn.clicked.connect(self._remove_source)
        src_btns.addWidget(add_btn)
        src_btns.addWidget(remove_btn)
        src_btns.addStretch(1)
        layout.addLayout(src_btns)

        form = QFormLayout()
        self._dest = QLineEdit(settings.destination.unc_path)
        form.addRow("Sunucu yolu:", self._dest)

        self._enabled = QCheckBox(
            "Günlük otomatik yedeklemeyi etkinleştir "
            "(kapalıysa yalnızca «Şimdi Yedekle» ile çalışır)"
        )
        self._enabled.setChecked(settings.schedule.enabled)
        self._enabled.setToolTip(
            "Kapalı: uygulama açılınca veya arka planda kendiliğinden yedek almaz.\n"
            "Açık: yalnızca aşağıda seçtiğiniz saatte günde bir kez otomatik yedekler."
        )
        form.addRow(self._enabled)

        self._time_edit = QTimeEdit()
        self._time_edit.setDisplayFormat("HH:mm")
        self._time_edit.setButtonSymbols(
            QAbstractSpinBox.ButtonSymbols.UpDownArrows
        )
        self._time_edit.setCorrectionMode(
            QAbstractSpinBox.CorrectionMode.CorrectToNearestValue
        )
        self._time_edit.setMinimumWidth(140)
        hour, minute = self._parse_time(settings.schedule.time)
        self._time_edit.setTime(QTime(hour, minute))
        form.addRow("Yedekleme saati:", self._time_edit)

        self._autostart = QCheckBox("Windows açılışında otomatik başlat")
        self._autostart.setChecked(settings.autostart.enabled)
        self._autostart.setToolTip(
            "Kullanıcı oturum açınca uygulamayı system tray'de başlatır "
            "(Task Scheduler, yönetici yetkisi gerekmez)."
        )
        form.addRow(self._autostart)

        self._retry_count = QSpinBox()
        self._retry_count.setRange(1, 20)
        self._retry_count.setButtonSymbols(
            QAbstractSpinBox.ButtonSymbols.UpDownArrows
        )
        self._retry_count.setMinimumWidth(140)
        self._retry_count.setValue(settings.retry.max_attempts)
        form.addRow("Retry sayısı:", self._retry_count)

        self._retry_delay = QSpinBox()
        self._retry_delay.setRange(0, 3600)
        self._retry_delay.setSuffix(" sn")
        self._retry_delay.setButtonSymbols(
            QAbstractSpinBox.ButtonSymbols.UpDownArrows
        )
        self._retry_delay.setMinimumWidth(140)
        self._retry_delay.setValue(settings.retry.initial_delay_seconds)
        form.addRow("Retry bekleme süresi:", self._retry_delay)

        self._zip_level = QSpinBox()
        self._zip_level.setRange(0, 9)
        self._zip_level.setButtonSymbols(
            QAbstractSpinBox.ButtonSymbols.UpDownArrows
        )
        self._zip_level.setMinimumWidth(140)
        self._zip_level.setValue(settings.zip.compresslevel)
        form.addRow("ZIP sıkıştırma seviyesi:", self._zip_level)
        layout.addLayout(form)

        self._hint = QLabel(
            "Ayarlar config/config.yaml dosyasına yazılır. "
            "PLACEHOLDER yollarla production yedekleme başlatılamaz. "
            "Önce Dashboard → Yapılandırmayı Test Et."
        )
        self._hint.setObjectName("Muted")
        self._hint.setWordWrap(True)
        layout.addWidget(self._hint)

        tool_row = QHBoxLayout()
        self._server_test_btn = QPushButton("Sunucu Bağlantısını Test Et")
        self._server_test_btn.setObjectName("SecondaryButton")
        self._server_test_btn.clicked.connect(self.server_test_requested.emit)
        tool_row.addWidget(self._server_test_btn)
        tool_row.addStretch(1)
        layout.addLayout(tool_row)

        self._save_btn = QPushButton("Ayarları Kaydet")
        self._save_btn.setObjectName("PrimaryButton")
        self._save_btn.clicked.connect(self._on_save)
        layout.addWidget(self._save_btn)
        layout.addStretch(1)

        self._test_mode = False
        self._add_btn = add_btn
        self._remove_btn = remove_btn
        self._reload_source_list()

    def set_test_mode(self, active: bool) -> None:
        """TEST MODE'da kalıcı config.yaml yazılmaz; oturum içi uygulama açıktır."""
        self._test_mode = bool(active)
        self._source_list.setEnabled(True)
        self._add_btn.setEnabled(True)
        self._remove_btn.setEnabled(True)
        self._dest.setReadOnly(False)
        self._enabled.setEnabled(True)
        self._time_edit.setEnabled(True)
        self._autostart.setEnabled(not self._test_mode)
        self._retry_count.setEnabled(True)
        self._retry_delay.setEnabled(True)
        self._zip_level.setEnabled(True)
        self._save_btn.setEnabled(True)
        if self._test_mode:
            self._hint.setText(
                "⚠ TEST MODU — alanları değiştirebilirsiniz. "
                "«Oturuma Uygula» yalnızca bu oturumu günceller; "
                "config.yaml ve Windows otomatik başlatma yazılmaz. "
                "Kalıcı kayıt için uygulamayı --test-mode olmadan açın."
            )
            self._save_btn.setText("Oturuma Uygula")
            self._save_btn.setToolTip(
                "TEST MODE: yalnızca bellek / bu oturum (config.yaml yok)"
            )
            self._autostart.setToolTip(
                "TEST MODE'da Windows otomatik başlatma değiştirilemez."
            )
        else:
            self._hint.setText(
                "Ayarlar config/config.yaml dosyasına yazılır. "
                "PLACEHOLDER yollarla production yedekleme başlatılamaz. "
                "Önce Dashboard → Yapılandırmayı Test Et."
            )
            self._save_btn.setText("Ayarları Kaydet")
            self._save_btn.setToolTip("")
            self._autostart.setToolTip(
                "Kullanıcı oturum açınca uygulamayı system tray'de başlatır "
                "(Task Scheduler, yönetici yetkisi gerekmez)."
            )

    def apply_settings(self, settings: AppSettings) -> None:
        self._settings = settings
        self._sources = list(settings.sources)
        self._dest.setText(settings.destination.unc_path)
        self._enabled.setChecked(settings.schedule.enabled)
        hour, minute = self._parse_time(settings.schedule.time)
        self._time_edit.setTime(QTime(hour, minute))
        self._autostart.setChecked(settings.autostart.enabled)
        self._retry_count.setValue(settings.retry.max_attempts)
        self._retry_delay.setValue(settings.retry.initial_delay_seconds)
        self._zip_level.setValue(settings.zip.compresslevel)
        self._reload_source_list()

    def _reload_source_list(self) -> None:
        self._source_list.clear()
        for source in self._sources:
            mark = "" if source.enabled else " [pasif]"
            QListWidgetItem(f"{source.path}{mark}", self._source_list)

    def _add_source(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Kaynak Klasör Seç")
        if not path:
            return
        for existing in self._sources:
            if existing.path.replace("\\", "/") == path.replace("\\", "/"):
                QMessageBox.information(self, "Ayarlar", "Bu klasör zaten listede.")
                return
        source_id = f"kaynak_{len(self._sources) + 1}"
        self._sources.append(SourceConfig(id=source_id, path=path, enabled=True))
        self._reload_source_list()

    def _remove_source(self) -> None:
        row = self._source_list.currentRow()
        if row < 0 or row >= len(self._sources):
            return
        del self._sources[row]
        self._reload_source_list()

    def _build_session_settings(self) -> AppSettings:
        """Formdan AppSettings üretir (dosyaya yazmaz)."""
        dest = self._dest.text().strip()
        if not dest:
            raise ConfigError("Sunucu / hedef yolu boş olamaz.")
        if not self._sources:
            raise ConfigError("En az bir kaynak klasörü tanımlanmalıdır.")
        qtime = self._time_edit.time()
        time_str = f"{qtime.hour():02d}:{qtime.minute():02d}"
        normalized_time = validate_schedule_time(time_str)
        retry_max = self._retry_count.value()
        retry_delay = self._retry_delay.value()
        zip_level = self._zip_level.value()
        if retry_max < 1 or retry_max > 20:
            raise ConfigError("Retry sayısı 1–20 arasında olmalıdır.")
        if retry_delay < 0 or retry_delay > 3600:
            raise ConfigError("Retry bekleme süresi 0–3600 saniye olmalıdır.")
        if zip_level < 0 or zip_level > 9:
            raise ConfigError("ZIP sıkıştırma seviyesi 0–9 arasında olmalıdır.")

        return replace(
            self._settings,
            sources=list(self._sources),
            destination=replace(self._settings.destination, unc_path=dest),
            schedule=replace(
                self._settings.schedule,
                enabled=self._enabled.isChecked(),
                time=normalized_time,
            ),
            retry=replace(
                self._settings.retry,
                max_attempts=retry_max,
                initial_delay_seconds=retry_delay,
            ),
            zip=replace(self._settings.zip, compresslevel=zip_level),
            autostart=replace(
                self._settings.autostart,
                enabled=self._autostart.isChecked(),
            ),
        )

    def _on_save(self) -> None:
        if self._test_mode:
            try:
                updated = self._build_session_settings()
            except ConfigError as exc:
                QMessageBox.warning(self, "Ayarlar", str(exc))
                return
            self.apply_settings(updated)
            self.settings_saved.emit(updated)
            QMessageBox.information(
                self,
                "Ayarlar",
                "Ayarlar bu TEST MODE oturumuna uygulandı.\n"
                "config.yaml dosyasına yazılmadı.\n"
                "Uygulamayı kapatınca bu değişiklikler kaybolur.",
            )
            return

        qtime = self._time_edit.time()
        time_str = f"{qtime.hour():02d}:{qtime.minute():02d}"
        want_autostart = self._autostart.isChecked()
        try:
            updated = save_runtime_settings(
                sources=self._sources,
                destination_unc=self._dest.text().strip(),
                schedule_enabled=self._enabled.isChecked(),
                schedule_time=time_str,
                retry_max_attempts=self._retry_count.value(),
                retry_delay_seconds=self._retry_delay.value(),
                zip_compresslevel=self._zip_level.value(),
                autostart_enabled=want_autostart,
            )
        except ConfigError as exc:
            QMessageBox.warning(self, "Ayar Kaydı", str(exc))
            return

        # Task Scheduler senkronu (registry Run kullanılmaz)
        try:
            from kurum_yedekleme.services.autostart import (
                AutostartError,
                sync_autostart,
            )

            sync_autostart(want_autostart)
        except AutostartError as exc:
            QMessageBox.warning(
                self,
                "Otomatik Başlatma",
                f"Ayarlar kaydedildi ancak Windows görevi güncellenemedi:\n\n{exc}",
            )
            self.apply_settings(updated)
            self.settings_saved.emit(updated)
            return

        self.apply_settings(updated)
        self.settings_saved.emit(updated)
        extra = (
            "\nWindows oturum açılışında tray'de başlatma: Açık."
            if want_autostart
            else "\nWindows oturum açılışında tray'de başlatma: Kapalı."
        )
        QMessageBox.information(
            self, "Ayarlar", "Ayarlar başarıyla kaydedildi." + extra
        )

    @staticmethod
    def _parse_time(value: str) -> tuple[int, int]:
        try:
            hour_s, minute_s = value.split(":")
            return int(hour_s), int(minute_s)
        except (ValueError, AttributeError):
            return 2, 0
