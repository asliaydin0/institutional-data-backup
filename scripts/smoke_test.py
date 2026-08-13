"""İskelet duman testi: modern UI + tray (offscreen)."""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("KURUM_YEDEKLEME_NO_TRAY", "1")


def run() -> int:
    from PySide6.QtWidgets import QApplication

    from kurum_yedekleme.config.loader import load_settings
    from kurum_yedekleme.db.connection import Database
    from kurum_yedekleme.db.history_repository import HistoryRepository
    from kurum_yedekleme.services.backup_service import BackupService
    from kurum_yedekleme.services.history_service import HistoryService
    from kurum_yedekleme.ui.main_window import MainWindow
    from kurum_yedekleme.ui.tray import TrayStatus, tray_supported
    from kurum_yedekleme.utils.logging_setup import setup_logging
    from kurum_yedekleme.utils.paths import resolve_under_root

    assert tray_supported() is False

    settings = load_settings()
    log_dir = resolve_under_root(settings.app.log_dir)
    data_dir = resolve_under_root(settings.app.data_dir)
    for d in (log_dir, data_dir):
        d.mkdir(parents=True, exist_ok=True)
    setup_logging(log_dir, settings.logging, also_console=False)

    db = Database(data_dir / "kurum_yedekleme.db")
    db.connect()
    db.initialize()
    history = HistoryService(HistoryRepository(db))
    backup = BackupService(settings, history_service=history)

    app = QApplication.instance() or QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    window = MainWindow(
        settings=settings,
        backup_service=backup,
        history_service=history,
        schedule_service=None,
        log_file=log_dir / "kurum_yedekleme.log",
    )
    window._missed_checked = True  # noqa: SLF001
    window.show()
    window._refresh_all()  # noqa: SLF001
    window._tray.set_status(TrayStatus.RUNNING)  # noqa: SLF001
    window._tray.set_status(TrayStatus.FAILED)  # noqa: SLF001
    window._tray.set_status(TrayStatus.SUCCESS)  # noqa: SLF001
    assert window._tray.status == TrayStatus.SUCCESS  # noqa: SLF001

    for index in range(window._nav.count()):  # noqa: SLF001
        window._nav.setCurrentRow(index)  # noqa: SLF001
        app.processEvents()

    # closeEvent: tray yokken onay ister — force quit yolu
    window._force_quit = True  # noqa: SLF001
    window.close()
    app.processEvents()

    # exec() yerine kısa processEvents döngüsü (offscreen güvenilir)
    end = time.time() + 0.2
    while time.time() < end:
        app.processEvents()
        time.sleep(0.01)

    db.close()
    print("SMOKE_OK", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
