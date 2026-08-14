"""Uygulama yaşam döngüsü ve giriş noktası."""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from typing import Optional

from kurum_yedekleme import __app_name__, __version__

logger = logging.getLogger(__name__)


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="kurum_yedekleme")
    parser.add_argument("--tray", action="store_true", help="System tray'de başlat.")
    parser.add_argument("--minimized", action="store_true", help="--tray ile aynı.")
    parser.add_argument(
        "--test-mode",
        action="store_true",
        help="Güvenli TEST MODE (tests/test_data). Gerçek kurum verisine dokunulmaz.",
    )
    parser.add_argument(
        "--run-test-backup",
        action="store_true",
        help="TEST MODE headless yedekleme akışı.",
    )
    parser.add_argument(
        "--smoke-gui",
        action="store_true",
        help="Kısa GUI duman testi.",
    )
    parser.add_argument(
        "--run-service",
        action="store_true",
        help="Windows Service / headless scheduler döngüsü (GUI yok).",
    )
    parser.add_argument(
        "--install-service",
        action="store_true",
        help="Windows Service kur (yönetici + pywin32).",
    )
    parser.add_argument(
        "--uninstall-service",
        action="store_true",
        help="Windows Service kaldır.",
    )
    return parser.parse_args(argv[1:])


def _is_test_mode(cli: argparse.Namespace) -> bool:
    return bool(cli.test_mode) or os.environ.get(
        "KURUM_YEDEKLEME_TEST_MODE", ""
    ).strip() in {"1", "true", "TRUE", "yes"}


def _run_gui(cli: argparse.Namespace) -> int:
    from PySide6.QtGui import QIcon
    from PySide6.QtWidgets import QApplication, QMessageBox

    from kurum_yedekleme.config.loader import ConfigError, load_settings
    from kurum_yedekleme.db.errors import DatabaseError
    from kurum_yedekleme.services.runtime import build_runtime
    from kurum_yedekleme.ui.main_window import MainWindow
    from kurum_yedekleme.utils.logging_setup import setup_logging
    from kurum_yedekleme.utils.paths import get_bundle_root, get_project_root

    test_mode = _is_test_mode(cli)
    qt_app = QApplication([sys.argv[0]])
    title = f"{__app_name__} [TEST MODE]" if test_mode else __app_name__
    qt_app.setApplicationName(title)
    qt_app.setApplicationVersion(__version__)
    qt_app.setQuitOnLastWindowClosed(False)

    icon_path = get_bundle_root() / "resources" / "app.ico"
    if not icon_path.is_file():
        icon_path = get_project_root() / "resources" / "app.ico"
    if icon_path.is_file():
        qt_app.setWindowIcon(QIcon(str(icon_path)))

    runtime = None
    try:
        if test_mode:
            from kurum_yedekleme.testing.fixtures import generate_test_source_data
            from kurum_yedekleme.testing.test_mode import (
                build_test_settings,
                ensure_test_directories,
                seed_test_areas,
            )

            os.environ["KURUM_YEDEKLEME_TEST_MODE"] = "1"
            paths = ensure_test_directories()
            generate_test_source_data(paths, force=False)
            settings = build_test_settings()
            setup_logging(paths.logs, settings.logging)
            runtime = build_runtime(settings, test_mode=True)
            seed_test_areas(runtime.areas, paths)
        else:
            settings = load_settings()
            runtime = build_runtime(settings, test_mode=False)
            setup_logging(runtime.log_dir, settings.logging)

        runtime.events.log_event(
            level="INFO",
            component="app",
            message=f"GUI başlatıldı (test_mode={test_mode}).",
        )
        window = MainWindow(
            runtime,
            log_file=runtime.log_dir / "kurum_yedekleme.log",
        )
        if test_mode:
            QMessageBox.warning(
                window,
                "⚠ TEST MODU AKTİF",
                "TEST MODU AKTİF\n\n"
                "Bu oturum gerçek kurum verilerine veya E:\\Yedekler "
                "üretim klasörüne yazmaz.\n"
                "Kaynak: tests/test_data/source\n"
                "Hedef: tests/test_data/yedekler",
            )
        if cli.tray or cli.minimized:
            if window._tray.is_available:  # noqa: SLF001
                window.hide()
            else:
                window.showMinimized()
        else:
            window.show()
        return int(qt_app.exec())
    except ConfigError as exc:
        QMessageBox.critical(None, "Yapılandırma Hatası", str(exc))
        return 1
    except DatabaseError as exc:
        QMessageBox.critical(None, "Veritabanı Hatası", str(exc))
        return 2
    except Exception as exc:  # noqa: BLE001
        logger.exception("Beklenmeyen hata")
        QMessageBox.critical(None, "Beklenmeyen Hata", str(exc))
        return 3
    finally:
        if runtime is not None:
            runtime.close()


def _run_smoke_gui() -> int:
    os.environ.setdefault("KURUM_YEDEKLEME_TEST_MODE", "1")
    from PySide6.QtWidgets import QApplication

    from kurum_yedekleme.services.runtime import build_runtime
    from kurum_yedekleme.testing.fixtures import generate_test_source_data
    from kurum_yedekleme.testing.test_mode import (
        build_test_settings,
        ensure_test_directories,
        seed_test_areas,
    )
    from kurum_yedekleme.ui.main_window import MainWindow
    from kurum_yedekleme.utils.logging_setup import setup_logging
    from kurum_yedekleme.utils.paths import get_project_root

    qt_app = QApplication([sys.argv[0]])
    qt_app.setQuitOnLastWindowClosed(True)
    paths = ensure_test_directories()
    generate_test_source_data(paths, force=False)
    settings = build_test_settings()
    setup_logging(paths.logs, settings.logging, also_console=False)
    runtime = build_runtime(settings, test_mode=True)
    seed_test_areas(runtime.areas, paths)
    window = MainWindow(runtime, log_file=paths.logs / "kurum_yedekleme.log")
    window.show()
    qt_app.processEvents()
    gui_ok = window.isVisible()
    end = time.time() + 0.6
    while time.time() < end:
        qt_app.processEvents()
        time.sleep(0.05)
    window._force_quit = True  # noqa: SLF001
    window.close()
    runtime.close()
    marker_dir = get_project_root() / "data"
    marker_dir.mkdir(parents=True, exist_ok=True)
    marker = marker_dir / "smoke_gui_ok.txt"
    status = "SMOKE_GUI_OK" if gui_ok else "SMOKE_GUI_FAIL"
    marker.write_text(status + "\n", encoding="utf-8")
    print(status)
    return 0 if gui_ok else 1


def main(argv: Optional[list[str]] = None) -> int:
    args_list = argv if argv is not None else sys.argv
    cli = _parse_args(args_list)

    if cli.install_service:
        from kurum_yedekleme.win_service import install_win32_service

        install_win32_service()
        return 0
    if cli.uninstall_service:
        from kurum_yedekleme.win_service import remove_win32_service

        remove_win32_service()
        return 0
    if cli.run_service:
        from kurum_yedekleme.service_host import run_service_loop

        return run_service_loop(test_mode=_is_test_mode(cli))
    if cli.run_test_backup:
        from kurum_yedekleme.testing.runner import run_test_mode_backup
        from kurum_yedekleme.utils.paths import get_project_root

        ok, report = run_test_mode_backup(force_regenerate=True, also_console=True)
        marker_dir = get_project_root() / "data"
        marker_dir.mkdir(parents=True, exist_ok=True)
        (marker_dir / "test_mode_last.txt").write_text(
            ("TEST_MODE_OK\n" if ok else "TEST_MODE_FAILED\n") + report,
            encoding="utf-8",
        )
        print(report)
        print("TEST_MODE_OK" if ok else "TEST_MODE_FAILED")
        return 0 if ok else 1
    if cli.smoke_gui:
        return _run_smoke_gui()
    return _run_gui(cli)


if __name__ == "__main__":
    raise SystemExit(main())
