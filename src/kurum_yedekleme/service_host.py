"""Windows Service / headless süreç döngüsü (Qt yok)."""

from __future__ import annotations

import logging
import os
import threading
import time
from typing import Optional

from kurum_yedekleme.config.loader import load_settings
from kurum_yedekleme.services.runtime import AppRuntime, build_runtime
from kurum_yedekleme.utils.logging_setup import setup_logging
from kurum_yedekleme.utils.paths import resolve_under_root

logger = logging.getLogger(__name__)


def is_test_mode_env() -> bool:
    return os.environ.get("KURUM_YEDEKLEME_TEST_MODE", "").strip() in {
        "1",
        "true",
        "TRUE",
        "yes",
    }


def run_service_loop(
    stop_event: Optional[threading.Event] = None,
    *,
    test_mode: Optional[bool] = None,
) -> int:
    """
    Scheduler + Backup Manager döngüsü.

    GUI bu fonksiyonu çağırmaz. Windows Service ve --run-service kullanır.
    """
    stop = stop_event or threading.Event()
    test = bool(test_mode) if test_mode is not None else is_test_mode_env()
    settings = load_settings() if not test else None
    runtime: Optional[AppRuntime] = None

    if test:
        from kurum_yedekleme.testing.fixtures import generate_test_source_data
        from kurum_yedekleme.testing.test_mode import (
            build_test_settings,
            ensure_test_directories,
            seed_test_areas,
        )

        paths = ensure_test_directories()
        generate_test_source_data(paths, force=False)
        settings = build_test_settings()
        setup_logging(paths.logs, settings.logging, also_console=False)
        runtime = build_runtime(settings, test_mode=True)
        seed_test_areas(runtime.areas, paths)
    else:
        assert settings is not None
        log_dir = resolve_under_root(settings.app.log_dir)
        log_dir.mkdir(parents=True, exist_ok=True)
        setup_logging(log_dir, settings.logging, also_console=False)
        runtime = build_runtime(settings, test_mode=False)

    assert runtime is not None
    logger.info("Kurum Yedekleme servis döngüsü başlıyor (test_mode=%s)", test)
    runtime.events.log_event(
        level="INFO",
        component="service",
        message="Windows Service / servis döngüsü başladı.",
    )
    runtime.schedule.start()
    runtime.retention_scheduler.start()
    try:
        while not stop.is_set():
            time.sleep(0.5)
        return 0
    finally:
        logger.info("Servis döngüsü duruyor")
        runtime.close()
