"""Ana uygulama penceresi."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import QTimer
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
from kurum_yedekleme.core.lock import BackupInProgressError
from kurum_yedekleme.core.progress import BackupProgressEvent
from kurum_yedekleme.db.models import BackupStatus, BackupType
from kurum_yedekleme.services.preflight import run_preflight
from kurum_yedekleme.services.runtime import AppRuntime
from kurum_yedekleme.services.windows_service import query_service
from kurum_yedekleme.ui.pages.about import AboutPage
from kurum_yedekleme.ui.pages.areas import AreasPage
from kurum_yedekleme.ui.pages.backup_page import BackupPage
from kurum_yedekleme.ui.pages.dashboard import DashboardPage
from kurum_yedekleme.ui.pages.history import HistoryPage
from kurum_yedekleme.ui.pages.logs_view import LogsPage
from kurum_yedekleme.ui.pages.settings import SettingsPage
from kurum_yedekleme.ui.theme import APP_STYLESHEET
from kurum_yedekleme.ui.tray import SystemTrayManager, TrayStatus
from kurum_yedekleme.ui.workers.backup_worker import BackupWorker

_NAV_ITEMS = (
    "Dashboard",
    "Yedekleme Alanları",
    "Yedekleme",
    "Geçmiş",
    "Ayarlar",
    "Loglar",
    "Hakkında",
)


class MainWindow(QMainWindow):
    def __init__(
        self,
        runtime: AppRuntime,
        *,
        log_file: Path | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._runtime = runtime
        self._settings = runtime.settings
        self._test_mode = runtime.test_mode
        self._worker: Optional[BackupWorker] = None
        self._force_quit = False

        title = f"{__app_name__} v{__version__}"
        if self._test_mode:
            title = f"{__app_name__} — ⚠ TEST MODU AKTİF v{__version__}"
        self.setWindowTitle(title)
        self.resize(1240, 780)
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
        self._areas_page = AreasPage(runtime.areas)
        self._backup_page = BackupPage()
        self._history_page = HistoryPage(history_service=runtime.history)
        self._settings_page = SettingsPage(self._settings)
        self._settings_page.set_test_mode(self._test_mode)
        self._logs_page = LogsPage(
            log_file=log_file,
            log_dir=log_file.parent if log_file is not None else None,
        )
        self._about_page = AboutPage()

        self._dashboard.backup_requested.connect(self._on_full_backup)
        self._dashboard.preflight_requested.connect(self._on_preflight)
        self._backup_page.backup_requested.connect(self._on_selected_backup)
        self._backup_page.cancel_requested.connect(self._on_cancel)
        self._areas_page.areas_changed.connect(self._refresh_all)
        self._settings_page.settings_saved.connect(self._on_settings_saved)

        self._stack = QStackedWidget()
        for page in (
            self._dashboard,
            self._areas_page,
            self._backup_page,
            self._history_page,
            self._settings_page,
            self._logs_page,
            self._about_page,
        ):
            self._stack.addWidget(page)
        root_layout.addWidget(self._stack, stretch=1)
        self._nav.currentRowChanged.connect(self._on_nav_changed)

        self._tray = SystemTrayManager(self)
        self._tray.open_dashboard.connect(self.show_dashboard)
        self._tray.backup_now.connect(self._on_full_backup)
        self._tray.show_last_backup.connect(self._show_last_backup_info)
        self._tray.open_settings.connect(self.show_settings)
        self._tray.open_logs.connect(self.show_logs)
        self._tray.quit_app.connect(self.request_quit)
        if self._tray.is_available:
            self._tray.show()

        if self._test_mode:
            self._runtime.schedule.start()
            self._runtime.retention_scheduler.start()

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refresh_all)
        self._timer.start(8000)

        self._refresh_all()

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        if self._force_quit:
            event.accept()
            return
        if self._tray.is_available:
            event.ignore()
            self.hide()
            if self._test_mode:
                tray_msg = (
                    "Arayüz arka planda. TEST MODU'nda otomatik yedekleme "
                    "pencere çalıştığı sürece devam eder."
                )
            else:
                tray_msg = (
                    "Arayüz arka planda. Otomatik yedekleme Windows Service "
                    "çalışıyorsa devam eder."
                )
            self._tray.notify(__app_name__, tray_msg)
            return
        event.accept()

    def request_quit(self) -> None:
        self._force_quit = True
        self._tray.hide()
        self.close()
        app = QApplication.instance()
        if app is not None:
            app.quit()

    def show_dashboard(self) -> None:
        self.show()
        self.raise_()
        self.activateWindow()
        self._nav.setCurrentRow(0)

    def show_settings(self) -> None:
        self.show()
        self.raise_()
        self.activateWindow()
        self._nav.setCurrentRow(4)

    def show_logs(self) -> None:
        self.show()
        self.raise_()
        self.activateWindow()
        self._nav.setCurrentRow(5)
        self._logs_page.reload()

    def _on_nav_changed(self, index: int) -> None:
        self._stack.setCurrentIndex(index)
        if index in {0, 1, 2, 3}:
            self._refresh_all()
        elif index == 5:
            self._logs_page.reload()

    def _on_settings_saved(self, settings: AppSettings) -> None:
        self._settings = settings
        try:
            self._runtime.backups.update_settings(settings)
        except BackupInProgressError as exc:
            QMessageBox.warning(self, "Ayarlar", str(exc))
            return
        self._runtime.schedule.update_schedule(settings.schedule)
        self._runtime.retention.update_settings(settings)
        self._runtime.retention_scheduler.update_retention(settings.retention)
        self._runtime.settings = settings
        if self._test_mode:
            if not self._runtime.schedule.is_running:
                self._runtime.schedule.start()
            if not self._runtime.retention_scheduler.is_running:
                self._runtime.retention_scheduler.start()
        self._refresh_all()

    def _refresh_all(self) -> None:
        areas = self._runtime.areas.list_areas()
        enabled = [a for a in areas if a.is_active]
        self._backup_page.set_areas(areas)
        self._history_page.set_areas(areas)
        last_map = {}
        for area in areas:
            if area.id is None:
                continue
            last = self._runtime.history.get_last_for_area(area.id)
            if last is not None:
                last_map[area.id] = last
        self._areas_page.set_last_backups(last_map)

        today = self._runtime.history.today_records()
        today_success = sum(1 for r in today if r.status == BackupStatus.SUCCESS)
        today_failed = sum(1 for r in today if r.status == BackupStatus.FAILED)
        last_auto = self._runtime.history.get_last_by_type(BackupType.AUTOMATIC)
        last_manual = self._runtime.history.get_last_by_type(BackupType.MANUAL)
        last_any = self._runtime.history.get_last_backup()
        failed = self._runtime.history.get_failed_backups(limit=1)
        last_error = failed[0] if failed else None
        missed = self._runtime.schedule.check_missed_backup() is not None
        service = query_service()
        self._dashboard.refresh(
            service=service,
            schedule_enabled=self._settings.schedule.enabled,
            schedule_time=self._settings.schedule.time,
            next_run=self._runtime.schedule.next_run_at(),
            missed=missed,
            active_areas=len(enabled),
            today_success=today_success,
            today_failed=today_failed,
            last_auto=last_auto,
            last_manual=last_manual,
            last_any=last_any,
            last_error=last_error,
            recent=self._runtime.history.get_last_n(8),
        )
        self._settings_page.refresh_service_status(service)
        self._history_page.refresh()
        self._sync_tray_status()
        busy = " | YEDEKLEME ÇALIŞIYOR" if self._runtime.backups.is_busy else ""
        auto_label = "Otomatik (oturum)" if self._test_mode else "Otomatik"
        self.statusBar().showMessage(
            f"Servis: {service.label_tr} | "
            f"{auto_label}: {'Açık' if self._settings.schedule.enabled else 'Kapalı'} "
            f"@ {self._settings.schedule.time}{busy}"
        )

    def _sync_tray_status(self) -> None:
        if self._runtime.backups.is_busy:
            self._tray.set_status(TrayStatus.RUNNING)
            return
        last = self._runtime.history.get_last_backup()
        if last is None:
            self._tray.set_status(TrayStatus.IDLE)
            return
        if last.status == BackupStatus.SUCCESS:
            self._tray.set_status(TrayStatus.SUCCESS)
        elif last.status == BackupStatus.FAILED:
            self._tray.set_status(TrayStatus.FAILED)
        else:
            self._tray.set_status(TrayStatus.IDLE)

    def _show_last_backup_info(self) -> None:
        last = self._runtime.history.get_last_backup()
        if last is None:
            QMessageBox.information(self, "Son Yedekleme", "Henüz kayıt yok.")
            return
        local = last.started_at.astimezone()
        QMessageBox.information(
            self,
            "Son Yedekleme",
            f"Alan: {last.area_name}\n"
            f"Tür: {last.backup_type.label_tr}\n"
            f"Durum: {last.status.label_tr}\n"
            f"Tarih: {local.strftime('%d.%m.%Y %H:%M:%S')}",
        )

    def _on_preflight(self) -> None:
        report = run_preflight(
            self._settings,
            self._runtime.areas.list_areas(),
            test_mode=self._test_mode,
        )
        body = report.format_user_report()
        if self._test_mode:
            body = "⚠ TEST MODU AKTİF\n\n" + body
        box = QMessageBox.information if report.ok else QMessageBox.warning
        box(self, "Yapılandırma Testi", body)

    def _on_full_backup(self) -> None:
        enabled = self._runtime.areas.list_enabled()
        self._start_backup(enabled)

    def _on_selected_backup(self, area_ids: list) -> None:
        if not area_ids:
            QMessageBox.information(
                self, "Yedekleme", "Lütfen en az bir alan seçin."
            )
            return
        selected = []
        for area in self._runtime.areas.list_areas():
            if area.id in area_ids and area.enabled:
                selected.append(area)
        self._start_backup(selected)

    def _on_cancel(self) -> None:
        if self._worker is not None:
            self._worker.cancel()

    def _start_backup(self, areas) -> None:
        if not areas:
            QMessageBox.information(
                self, "Yedekleme", "Yedeklenecek aktif alan yok."
            )
            return
        if self._runtime.backups.is_busy or (
            self._worker is not None and self._worker.isRunning()
        ):
            QMessageBox.information(
                self,
                "Yedekleme",
                "Şu anda başka bir yedekleme devam ediyor.",
            )
            return
        self._set_ui_busy(True)
        self._tray.set_status(TrayStatus.RUNNING)
        self._nav.setCurrentRow(2)
        self._worker = BackupWorker(
            self._runtime.backups, areas, backup_type=BackupType.MANUAL
        )
        self._worker.progress.connect(self._on_progress)
        self._worker.finished_ok.connect(
            lambda msg: self._on_worker_done(msg, ok=True)
        )
        self._worker.finished_error.connect(
            lambda msg: self._on_worker_done(msg, ok=False)
        )
        self._worker.start()

    def _on_progress(self, event: object) -> None:
        if isinstance(event, BackupProgressEvent):
            self._dashboard.apply_progress(event)
            self._backup_page.apply_progress(event)

    def _set_ui_busy(self, busy: bool) -> None:
        self._dashboard.set_busy(busy)
        self._backup_page.set_busy(busy)

    def _on_worker_done(self, message: str, *, ok: bool) -> None:
        self._set_ui_busy(False)
        self._refresh_all()
        self._logs_page.reload()
        if not self.isVisible():
            self._tray.notify(
                "Yedekleme Başarılı" if ok else "Yedekleme Hatası",
                message[:180],
            )
            return
        if ok:
            QMessageBox.information(self, "Yedekleme", message)
        else:
            QMessageBox.warning(self, "Yedekleme", message)
