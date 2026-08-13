"""Ana uygulama penceresi — modern kurumsal arayüz + system tray."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from kurum_yedekleme import __app_name__, __version__
from kurum_yedekleme.config.schema import AppSettings
from kurum_yedekleme.core.progress import BackupProgressEvent
from kurum_yedekleme.db.models import BackupStatus
from kurum_yedekleme.services.app_state import AppStateStore
from kurum_yedekleme.services.backup_service import BackupService
from kurum_yedekleme.services.history_service import HistoryService
from kurum_yedekleme.services.preflight import (
    probe_destination_writable,
    run_preflight,
)
from kurum_yedekleme.services.schedule_service import ScheduleService
from kurum_yedekleme.utils.windows_paths import to_path
from kurum_yedekleme.ui.pages.about import AboutPage
from kurum_yedekleme.ui.pages.backup_page import BackupPage
from kurum_yedekleme.ui.pages.dashboard import DashboardPage
from kurum_yedekleme.ui.pages.history import HistoryPage
from kurum_yedekleme.ui.pages.logs_view import LogsPage
from kurum_yedekleme.ui.pages.settings import SettingsPage
from kurum_yedekleme.ui.theme import APP_STYLESHEET
from kurum_yedekleme.ui.tray import SystemTrayManager, TrayStatus
from kurum_yedekleme.ui.workers.backup_worker import BackupWorker
from kurum_yedekleme.utils.formatting import format_bytes

_NAV_ITEMS = (
    "Dashboard",
    "Yedekleme",
    "Geçmiş",
    "Ayarlar",
    "Loglar",
    "Hakkında",
)


class MainWindow(QMainWindow):
    """Türkçe masaüstü arayüz — kapatınca tray'e iner, scheduler devam eder."""

    def __init__(
        self,
        settings: AppSettings,
        backup_service: BackupService,
        *,
        history_service: HistoryService | None = None,
        schedule_service: ScheduleService | None = None,
        app_state_store: AppStateStore | None = None,
        test_mode: bool = False,
        log_file: Path | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._settings = settings
        self._backup_service = backup_service
        self._history_service = history_service
        self._schedule_service = schedule_service
        self._app_state = app_state_store
        self._test_mode = bool(test_mode)
        self._log_file = log_file
        self._worker: Optional[BackupWorker] = None
        self._missed_checked = False
        self._force_quit = False

        title = f"{__app_name__} v{__version__}"
        if self._test_mode:
            title = f"{__app_name__} — ⚠ TEST MODU AKTİF v{__version__}"
        self.setWindowTitle(title)
        self.resize(1180, 760)
        self.setStyleSheet(APP_STYLESHEET)

        root = QWidget()
        self.setCentralWidget(root)
        root_layout = QHBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        sidebar = QFrame()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(220)
        side_layout = QVBoxLayout(sidebar)
        side_layout.setContentsMargins(12, 20, 12, 16)
        brand = QLabel(__app_name__)
        brand.setObjectName("BrandTitle")
        brand.setWordWrap(True)
        sub = QLabel(
            "⚠ TEST MODU AKTİF" if self._test_mode else "Kurumsal yedekleme"
        )
        sub.setObjectName("BrandSubtitle")
        if not self._test_mode:
            sub.setStyleSheet("color: #94a3b8; background: transparent;")
        side_layout.addWidget(brand)
        side_layout.addWidget(sub)
        side_layout.addSpacing(16)

        self._nav = QListWidget()
        self._nav.setObjectName("NavList")
        for label in _NAV_ITEMS:
            QListWidgetItem(label, self._nav)
        self._nav.setCurrentRow(0)
        side_layout.addWidget(self._nav, stretch=1)
        root_layout.addWidget(sidebar)

        self._dashboard = DashboardPage()
        self._dashboard.set_test_mode(self._test_mode)
        self._backup_page = BackupPage()
        self._history_page = HistoryPage(history_service=history_service)
        self._settings_page = SettingsPage(settings)
        self._settings_page.set_test_mode(self._test_mode)
        self._logs_page = LogsPage(
            log_file=log_file,
            log_dir=log_file.parent if log_file is not None else None,
        )
        self._about_page = AboutPage()

        self._dashboard.backup_requested.connect(self._on_manual_backup)
        self._dashboard.preflight_requested.connect(self._on_preflight)
        self._dashboard.server_test_requested.connect(self._on_server_test)
        self._backup_page.backup_requested.connect(self._on_manual_backup)
        self._settings_page.settings_saved.connect(self._on_settings_saved)
        self._settings_page.server_test_requested.connect(self._on_server_test)

        self._stack = QStackedWidget()
        for page in (
            self._dashboard,
            self._backup_page,
            self._history_page,
            self._settings_page,
            self._logs_page,
            self._about_page,
        ):
            self._stack.addWidget(page)
        root_layout.addWidget(self._stack, stretch=1)

        self._nav.currentRowChanged.connect(self._on_nav_changed)

        # System tray
        self._tray = SystemTrayManager(self)
        self._tray.open_dashboard.connect(self.show_dashboard)
        self._tray.backup_now.connect(self._on_manual_backup)
        self._tray.show_last_backup.connect(self._show_last_backup_info)
        self._tray.open_settings.connect(self.show_settings)
        self._tray.open_logs.connect(self.show_logs)
        self._tray.quit_app.connect(self.request_quit)
        if self._tray.is_available:
            self._tray.show()
        # Offscreen / traysiz ortamlarda uyarı diyaloğu gösterme (testleri kilitlemesin)

        self._refresh_all()
        self._update_status_bar()
        self._sync_tray_status()

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        if not self._missed_checked:
            self._missed_checked = True
            self._check_missed_backup_prompt()

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        """X ile kapatma → tray'e gizle (scheduler çalışmaya devam eder)."""
        if self._force_quit:
            event.accept()
            return
        if self._tray.is_available:
            event.ignore()
            self.hide()
            self._tray.notify(
                __app_name__,
                "Uygulama arka planda çalışmaya devam ediyor.\n"
                "Tamamen kapatmak için tray menüsünden "
                "\"Uygulamayı Kapat\" seçin.",
            )
            return
        # Tray yoksa onay iste
        if self._confirm_quit():
            event.accept()
        else:
            event.ignore()

    def request_quit(self) -> None:
        """Tray üzerinden tam kapanış (onaylı)."""
        if not self._confirm_quit():
            return
        self._force_quit = True
        self._tray.hide()
        self.close()
        app = QApplication.instance()
        if app is not None:
            app.quit()

    def _confirm_quit(self) -> bool:
        answer = QMessageBox.question(
            self if self.isVisible() else None,
            "Uygulamayı Kapat",
            "Uygulamayı tamamen kapatmak istediğinize emin misiniz?\n\n"
            "Zamanlanmış yedeklemeler bu bilgisayarda "
            "uygulama kapalıyken çalışmaz.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return answer == QMessageBox.StandardButton.Yes

    def show_dashboard(self) -> None:
        self.show()
        self.raise_()
        self.activateWindow()
        self._nav.setCurrentRow(0)
        self._stack.setCurrentIndex(0)
        self._refresh_all()

    def show_settings(self) -> None:
        self.show()
        self.raise_()
        self.activateWindow()
        self._nav.setCurrentRow(3)
        self._stack.setCurrentIndex(3)

    def show_logs(self) -> None:
        self.show()
        self.raise_()
        self.activateWindow()
        self._nav.setCurrentRow(4)
        self._stack.setCurrentIndex(4)
        self._logs_page.reload()

    def _show_last_backup_info(self) -> None:
        if self._history_service is None:
            QMessageBox.information(self, "Son Yedekleme", "Geçmiş servisi yok.")
            return
        last = self._history_service.get_last_backup()
        if last is None:
            QMessageBox.information(
                self if self.isVisible() else None,
                "Son Yedekleme",
                "Henüz yedekleme kaydı yok.",
            )
            return
        local = last.backup_start_time.astimezone()
        text = (
            f"Durum: {last.status.value}\n"
            f"Tarih: {local.strftime('%d.%m.%Y %H:%M:%S')}\n"
            f"Dosya: {last.file_count}\n"
            f"ZIP: {format_bytes(last.compressed_size)}\n"
            f"Hedef: {last.destination_path or '—'}"
        )
        if last.error_message:
            text += f"\n\nNot: {last.error_message}"
        QMessageBox.information(
            self if self.isVisible() else None,
            "Son Yedekleme",
            text,
        )

    def _on_nav_changed(self, index: int) -> None:
        self._stack.setCurrentIndex(index)
        if index == 0:
            self._refresh_all()
        elif index == 2:
            self._history_page.refresh()
        elif index == 4:
            self._logs_page.reload()

    def _on_settings_saved(self, settings: AppSettings) -> None:
        self._settings = settings
        try:
            self._backup_service.update_settings(settings)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Ayarlar", str(exc))
            return
        if self._schedule_service is not None:
            self._schedule_service.update_schedule(settings.schedule)
        self._settings_page.apply_settings(settings)
        self._refresh_all()
        self._update_status_bar()

    def _update_status_bar(self) -> None:
        sch = self._settings.schedule
        busy = " | YEDEKLEME ÇALIŞIYOR" if self._backup_service.is_busy else ""
        self.statusBar().showMessage(
            f"Otomatik: {'Açık' if sch.enabled else 'Kapalı'} @ {sch.time}{busy}"
            f" | Tray: arka plan aktif"
        )

    def _sync_tray_status(self) -> None:
        if self._backup_service.is_busy:
            self._tray.set_status(TrayStatus.RUNNING)
            return
        if self._history_service is None:
            self._tray.set_status(TrayStatus.IDLE)
            return
        last = self._history_service.get_last_backup()
        if last is None:
            self._tray.set_status(TrayStatus.IDLE)
            return
        if last.status == BackupStatus.SUCCESS:
            local = last.backup_start_time.astimezone()
            self._tray.set_status(
                TrayStatus.SUCCESS,
                detail=local.strftime("%d.%m.%Y %H:%M"),
            )
        elif last.status == BackupStatus.FAILED:
            self._tray.set_status(
                TrayStatus.FAILED,
                detail=(last.error_message or "")[:80],
            )
        elif last.status == BackupStatus.RUNNING:
            self._tray.set_status(TrayStatus.RUNNING)
        else:
            self._tray.set_status(TrayStatus.IDLE)

    def _refresh_all(self) -> None:
        last_ok = None
        last_any = None
        recent: list = []
        if self._history_service is not None:
            last_ok = self._history_service.get_last_successful()
            last_any = self._history_service.get_last_backup()
            recent = self._history_service.get_last_n(8)

        next_run = None
        if self._schedule_service is not None:
            next_run = self._schedule_service.next_run_at()

        self._dashboard.refresh(
            settings=self._settings,
            system_active=True,
            last_success=last_ok,
            last_any=last_any,
            recent=recent,
            next_run=next_run,
        )
        if not self._settings.schedule.enabled:
            self._dashboard.card_system.set_value("Aktif (otomatik kapalı)")
        self._sync_tray_status()

    def _on_manual_backup(self) -> None:
        self._start_backup_job(trigger="manual", notify=True)

    def _on_preflight(self) -> None:
        try:
            report = run_preflight(
                self._settings,
                require_production_config=not self._test_mode,
            )
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(
                self,
                "Yapılandırma Testi",
                f"Test çalıştırılamadı:\n\n{exc}",
            )
            return
        title = "Yapılandırma Testi"
        body = report.format_user_report()
        if self._test_mode:
            body = (
                "⚠ TEST MODU — yerel test_data / test_server kontrol edildi.\n"
                "Production config kuralları uygulanmadı.\n\n"
                + body
            )
        if report.ok:
            QMessageBox.information(self, title, body)
        else:
            QMessageBox.warning(self, title, body)

    def _on_server_test(self) -> None:
        dest = to_path(self._settings.destination.unc_path)
        try:
            ok, detail = probe_destination_writable(dest)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(
                self,
                "Sunucu Bağlantısı",
                f"Test çalıştırılamadı:\n\n{exc}",
            )
            return
        prefix = (
            "⚠ TEST MODU — yerel test_server klasörü\n\n"
            if self._test_mode
            else ""
        )
        if ok:
            QMessageBox.information(
                self,
                "Sunucu Bağlantısı",
                f"{prefix}"
                f"✓ Sunucu erişilebilir\n"
                f"✓ Yazma izni var\n\n"
                f"Hedef: {dest}\n"
                f"Ayrıntı: {detail}\n\n"
                "Test dosyası oluşturulup silindi; gerçek yedek alınmadı.",
            )
        else:
            QMessageBox.warning(
                self,
                "Sunucu Bağlantısı",
                f"{prefix}"
                f"✗ Sunucu bağlantı/yazma testi başarısız.\n\n"
                f"Hedef: {dest}\n"
                f"Ayrıntı: {detail}",
            )

    def _start_backup_job(self, *, trigger: str, notify: bool) -> None:
        if self._backup_service.is_busy or (
            self._worker is not None and self._worker.isRunning()
        ):
            target = self if self.isVisible() else None
            QMessageBox.information(
                target,
                "Yedekleme",
                "Şu anda başka bir yedekleme devam ediyor.",
            )
            return

        # İlk production yedek onayı
        if (
            not self._test_mode
            and self._app_state is not None
            and self._app_state.is_first_production_backup_pending()
            and self.isVisible()
        ):
            answer = QMessageBox.question(
                self,
                "Gerçek Yedekleme Onayı",
                "Bu işlem gerçek kurumsal verileri yedekleyecek.\n"
                "Devam etmek istiyor musunuz?\n\n"
                "Öneri: Önce «Yapılandırmayı Test Et» çalıştırın.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return

        self._set_ui_busy(True)
        self._tray.set_status(TrayStatus.RUNNING)
        self.statusBar().showMessage("Yedekleme arka planda çalışıyor...")
        if self.isVisible():
            self._stack.setCurrentIndex(1)
            self._nav.setCurrentRow(1)

        self._worker = BackupWorker(self._backup_service, trigger=trigger)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished_ok.connect(
            lambda msg: self._on_worker_done(msg, ok=True, notify=notify)
        )
        self._worker.finished_error.connect(
            lambda msg: self._on_worker_done(msg, ok=False, notify=True)
        )
        self._worker.start()

    def _on_progress(self, event: object) -> None:
        if not isinstance(event, BackupProgressEvent):
            return
        self._dashboard.apply_progress(event)
        self._backup_page.apply_progress(event)

    def _set_ui_busy(self, busy: bool) -> None:
        self._dashboard.set_busy(busy)
        self._backup_page.set_busy(busy)

    def _on_worker_done(self, message: str, *, ok: bool, notify: bool) -> None:
        self._set_ui_busy(False)
        self._update_status_bar()
        self._history_page.refresh()
        self._refresh_all()
        self._logs_page.reload()
        self._sync_tray_status()

        if (
            ok
            and not self._test_mode
            and self._app_state is not None
            and self._app_state.is_first_production_backup_pending()
        ):
            self._app_state.mark_first_production_backup_done()

        if not notify:
            return

        # Pencere gizliyse tray bildirimi; açıksa diyalog
        if not self.isVisible():
            title = "Yedekleme Başarılı" if ok else "Yedekleme Hatası"
            short = message if len(message) < 180 else message[:177] + "..."
            self._tray.notify(title, short)
            return

        if ok:
            QMessageBox.information(self, "Yedekleme Başarılı", message)
        else:
            QMessageBox.warning(self, "Yedekleme Hatası", message)

    def _check_missed_backup_prompt(self) -> None:
        if self._schedule_service is None:
            return
        info = self._schedule_service.check_missed_backup()
        if info is None:
            return

        self._schedule_service.acknowledge_missed_prompt(info.today)
        answer = QMessageBox.question(
            self,
            "Kaçırılmış Yedekleme",
            info.message
            + "\n\nHayır derseniz şimdi yedek alınmaz; "
            "isterseniz Dashboard’dan elle başlatabilirsiniz.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self._schedule_service.mark_auto_run_for_today(info.today)
            self._start_backup_job(trigger="schedule", notify=True)
