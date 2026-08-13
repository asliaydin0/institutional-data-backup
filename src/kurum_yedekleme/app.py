"""Uygulama yaşam döngüsü ve giriş noktası."""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from pathlib import Path
from typing import Optional

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMessageBox

from kurum_yedekleme import __app_name__, __version__
from kurum_yedekleme.config.loader import ConfigError, load_settings
from kurum_yedekleme.config.schema import AppSettings
from kurum_yedekleme.db.connection import Database
from kurum_yedekleme.db.errors import DatabaseError
from kurum_yedekleme.db.history_repository import HistoryRepository
from kurum_yedekleme.db.repository import Repository
from kurum_yedekleme.services.app_state import AppStateStore
from kurum_yedekleme.services.backup_service import BackupService
from kurum_yedekleme.services.history_service import HistoryService
from kurum_yedekleme.services.schedule_service import ScheduleService
from kurum_yedekleme.services.schedule_state import ScheduleStateStore
from kurum_yedekleme.ui.main_window import MainWindow
from kurum_yedekleme.utils.logging_setup import setup_logging
from kurum_yedekleme.utils.paths import get_bundle_root, get_project_root, resolve_under_root

logger = logging.getLogger(__name__)


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="kurum_yedekleme")
    parser.add_argument(
        "--tray",
        action="store_true",
        help="Pencereyi gizleyerek system tray'de başlat (oturum açılışı).",
    )
    parser.add_argument(
        "--minimized",
        action="store_true",
        help="--tray ile aynı (geriye dönük uyumluluk).",
    )
    parser.add_argument(
        "--test-mode",
        action="store_true",
        help=(
            "Güvenli TEST MODE: yalnızca tests/test_data ve test_server. "
            "Gerçek kurum verisine / UNC sunucusuna dokunulmaz."
        ),
    )
    parser.add_argument(
        "--run-test-backup",
        action="store_true",
        help="TEST MODE headless tam yedekleme akışını çalıştırıp çık (GUI yok).",
    )
    parser.add_argument(
        "--smoke-gui",
        action="store_true",
        help="Paketlenmiş EXE için kısa GUI/tray/SQLite duman testi (otomatik kapanır).",
    )
    return parser.parse_args(argv[1:])


def _load_settings_for_mode(*, test_mode: bool) -> AppSettings:
    if not test_mode:
        return load_settings()

    from kurum_yedekleme.testing.fixtures import generate_test_source_data
    from kurum_yedekleme.testing.test_mode import (
        build_test_settings,
        ensure_test_directories,
        resolve_test_paths,
        validate_test_settings,
    )

    paths = ensure_test_directories()
    generate_test_source_data(paths, force=False)
    settings = build_test_settings()
    validate_test_settings(settings, resolve_test_paths())
    os.environ["KURUM_YEDEKLEME_TEST_MODE"] = "1"
    return settings


def _apply_window_icon(app: QApplication) -> None:
    icon_path = get_bundle_root() / "resources" / "app.ico"
    if not icon_path.is_file():
        icon_path = get_project_root() / "resources" / "app.ico"
    if icon_path.is_file():
        app.setWindowIcon(QIcon(str(icon_path)))


def _run_smoke_gui() -> int:
    """
    EXE doğrulama: GUI açılır, tray kurulur, SQLite yazılır, kısa süre sonra çıkar.
    Sonucu data/smoke_gui_ok.txt dosyasına yazar (windowed stdout yok).
    """
    os.environ.setdefault("KURUM_YEDEKLEME_TEST_MODE", "1")
    qt_app = QApplication([sys.argv[0]])
    qt_app.setApplicationName(f"{__app_name__} Smoke")
    qt_app.setQuitOnLastWindowClosed(True)
    _apply_window_icon(qt_app)

    settings = _load_settings_for_mode(test_mode=True)
    log_dir = resolve_under_root(settings.app.log_dir)
    data_dir = resolve_under_root(settings.app.data_dir)
    for d in (log_dir, data_dir):
        d.mkdir(parents=True, exist_ok=True)
    setup_logging(log_dir, settings.logging, also_console=False)

    db = Database(data_dir / "smoke_gui.db")
    db.connect()
    db.initialize()
    history = HistoryService(HistoryRepository(db))
    backup = BackupService(settings, history_service=history, test_mode=True)

    window = MainWindow(
        settings=settings,
        backup_service=backup,
        history_service=history,
        schedule_service=None,
        test_mode=True,
        log_file=log_dir / "kurum_yedekleme.log",
    )
    window._missed_checked = True  # noqa: SLF001
    window.show()
    qt_app.processEvents()

    tray_ok = bool(window._tray.is_available)  # noqa: SLF001
    # Offscreen CI'da tray olmayabilir; gerçek masaüstünde beklenir
    gui_ok = window.isVisible()
    db_ok = (data_dir / "smoke_gui.db").is_file()

    # Kısa olay döngüsü
    end = time.time() + 0.8
    while time.time() < end:
        qt_app.processEvents()
        time.sleep(0.05)

    window._force_quit = True  # noqa: SLF001
    window.close()
    qt_app.processEvents()
    db.close()

    marker_dir = get_project_root() / "data"
    marker_dir.mkdir(parents=True, exist_ok=True)
    marker = marker_dir / "smoke_gui_ok.txt"
    lines = [
        "SMOKE_GUI_OK" if (gui_ok and db_ok) else "SMOKE_GUI_FAIL",
        f"gui_visible={gui_ok}",
        f"tray_available={tray_ok}",
        f"sqlite={db_ok}",
        f"db_path={data_dir / 'smoke_gui.db'}",
    ]
    marker.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 0 if (gui_ok and db_ok) else 1


def main(argv: Optional[list[str]] = None) -> int:
    """
    Uygulamayı başlatır.

    --tray: GUI kapalı, tray + scheduler arka planda.
    --test-mode: güvenli örnek veri + yerel test_server.
    --run-test-backup: headless TEST MODE akışı.
    --smoke-gui: paketlenmiş EXE duman testi.
    """
    args_list = argv if argv is not None else sys.argv
    cli = _parse_args(args_list)

    if cli.smoke_gui:
        return _run_smoke_gui()

    if cli.run_test_backup:
        from kurum_yedekleme.testing.runner import run_test_mode_backup

        ok, report = run_test_mode_backup(force_regenerate=True, also_console=True)
        # Windowed EXE'de stdout görünmeyebilir — marker dosyası
        marker_dir = get_project_root() / "data"
        marker_dir.mkdir(parents=True, exist_ok=True)
        marker = marker_dir / "test_mode_last.txt"
        marker.write_text(
            ("TEST_MODE_OK\n" if ok else "TEST_MODE_FAILED\n") + report,
            encoding="utf-8",
        )
        print(report)
        if ok:
            print("TEST_MODE_OK")
            return 0
        print("TEST_MODE_FAILED")
        return 1

    start_in_tray = bool(cli.tray or cli.minimized)
    test_mode = bool(cli.test_mode) or os.environ.get(
        "KURUM_YEDEKLEME_TEST_MODE", ""
    ).strip() in {"1", "true", "TRUE", "yes"}

    qt_app = QApplication([args_list[0]])
    title = f"{__app_name__} [TEST MODE]" if test_mode else __app_name__
    qt_app.setApplicationName(title)
    qt_app.setApplicationVersion(__version__)
    qt_app.setQuitOnLastWindowClosed(False)
    _apply_window_icon(qt_app)

    database: Optional[Database] = None
    schedule_service: Optional[ScheduleService] = None

    try:
        settings = _load_settings_for_mode(test_mode=test_mode)

        log_dir = resolve_under_root(settings.app.log_dir)
        data_dir = resolve_under_root(settings.app.data_dir)
        temp_dir = resolve_under_root(settings.app.temp_dir)

        for directory in (log_dir, data_dir, temp_dir):
            directory.mkdir(parents=True, exist_ok=True)

        setup_logging(log_dir, settings.logging)
        logger.info(
            "%s v%s başlatılıyor (tray=%s, test_mode=%s)",
            title,
            __version__,
            start_in_tray,
            test_mode,
        )

        db_path = data_dir / "kurum_yedekleme.db"
        database = Database(db_path)
        database.connect()
        database.initialize()

        event_repo = Repository(database)
        event_repo.log_event(
            level="INFO",
            component="app",
            message=(
                f"Uygulama başlatıldı (tray={start_in_tray}, test_mode={test_mode})."
            ),
        )

        history_service = HistoryService(HistoryRepository(database))
        backup_service = BackupService(
            settings,
            history_service=history_service,
            test_mode=test_mode,
        )
        state_store = ScheduleStateStore(database)
        app_state = AppStateStore(database)
        schedule_service = ScheduleService(
            settings.schedule,
            backup_service,
            state_store=state_store,
            history_service=history_service,
            poll_interval_seconds=20.0,
        )
        schedule_service.start()

        window = MainWindow(
            settings=settings,
            backup_service=backup_service,
            history_service=history_service,
            schedule_service=schedule_service,
            app_state_store=app_state,
            test_mode=test_mode,
            log_file=log_dir / "kurum_yedekleme.log",
        )
        if test_mode:
            window.setWindowTitle(
                f"{__app_name__} — ⚠ TEST MODU AKTİF v{__version__}"
            )
        if start_in_tray:
            window._missed_checked = True  # noqa: SLF001
            if window._tray.is_available:  # noqa: SLF001
                window.hide()
                window._tray.notify(  # noqa: SLF001
                    title,
                    "Arka planda çalışıyor. Dashboard için tray simgesine tıklayın.",
                )
            else:
                window.showMinimized()
        else:
            window.show()
            if test_mode:
                QMessageBox.warning(
                    window,
                    "⚠ TEST MODU AKTİF",
                    "TEST MODU AKTİF\n\n"
                    "Bu oturum gerçek kurum verilerine veya üretim UNC "
                    "sunucusuna bağlanmaz.\n"
                    "Kaynak: tests/test_data/source\n"
                    "Hedef: test_server/\n\n"
                    "Production için uygulamayı --test-mode ve "
                    "KURUM_YEDEKLEME_TEST_MODE OLMADAN başlatın.\n\n"
                    "Yanlışlıkla production makinesinde bu modu kullanmayın.",
                )

        exit_code = qt_app.exec()
        logger.info("Uygulama kapanıyor (kod=%s)", exit_code)
        return int(exit_code)

    except ConfigError as exc:
        logger.exception("Yapılandırma hatası")
        QMessageBox.critical(
            None,
            "Yapılandırma Hatası",
            f"Yapılandırma yüklenemedi:\n\n{exc}",
        )
        return 1
    except DatabaseError as exc:
        logger.exception("Veritabanı hatası")
        QMessageBox.critical(
            None,
            "Veritabanı Hatası",
            f"Veritabanı başlatılamadı:\n\n{exc}",
        )
        return 2
    except Exception as exc:  # noqa: BLE001
        logger.exception("Beklenmeyen hata")
        QMessageBox.critical(
            None,
            "Beklenmeyen Hata",
            f"Uygulama başlatılırken hata oluştu:\n\n{exc}",
        )
        return 3
    finally:
        if schedule_service is not None:
            schedule_service.stop()
        if database is not None:
            database.close()


if __name__ == "__main__":
    raise SystemExit(main())
