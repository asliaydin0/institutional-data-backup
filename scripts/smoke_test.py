"""İskelet duman testi: modern UI (offscreen)."""

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
os.environ.setdefault("KURUM_YEDEKLEME_TEST_MODE", "1")


def run() -> int:
    from PySide6.QtWidgets import QApplication

    from kurum_yedekleme.services.runtime import build_runtime
    from kurum_yedekleme.testing.fixtures import generate_test_source_data
    from kurum_yedekleme.testing.test_mode import (
        build_test_settings,
        ensure_test_directories,
        seed_test_areas,
    )
    from kurum_yedekleme.ui.main_window import MainWindow
    from kurum_yedekleme.ui.tray import TrayStatus, tray_supported
    from kurum_yedekleme.utils.logging_setup import setup_logging

    assert tray_supported() is False

    paths = ensure_test_directories()
    generate_test_source_data(paths, force=False)
    settings = build_test_settings()
    setup_logging(paths.logs, settings.logging, also_console=False)
    runtime = build_runtime(settings, test_mode=True)
    seed_test_areas(runtime.areas, paths)

    app = QApplication.instance() or QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    window = MainWindow(runtime, log_file=paths.logs / "kurum_yedekleme.log")
    window.show()
    window._refresh_all()  # noqa: SLF001
    window._tray.set_status(TrayStatus.RUNNING)  # noqa: SLF001
    window._tray.set_status(TrayStatus.SUCCESS)  # noqa: SLF001
    assert window._tray.status == TrayStatus.SUCCESS  # noqa: SLF001

    for index in range(window._nav.count()):  # noqa: SLF001
        window._nav.setCurrentRow(index)  # noqa: SLF001
        app.processEvents()

    window._force_quit = True  # noqa: SLF001
    window.close()
    app.processEvents()

    end = time.time() + 0.2
    while time.time() < end:
        app.processEvents()
        time.sleep(0.01)

    runtime.close()
    print("SMOKE_OK", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
