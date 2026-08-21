from __future__ import annotations

from pathlib import Path

from kurum_yedekleme.utils.app_logger import get_logger
from kurum_yedekleme.utils.logging_setup import (
    LOG_FILE_NAME,
    SERVICE_LOG_FILE_NAME,
    setup_logging,
)


def test_service_logs_are_mirrored_to_gui_file(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    setup_logging(
        log_dir,
        also_console=False,
        file_name=SERVICE_LOG_FILE_NAME,
        mirror_file_name=LOG_FILE_NAME,
    )
    get_logger("BackupScheduler").info(
        "Otomatik yedekleme başlıyor",
        operation="start",
    )
    service_text = (log_dir / SERVICE_LOG_FILE_NAME).read_text(encoding="utf-8")
    gui_text = (log_dir / LOG_FILE_NAME).read_text(encoding="utf-8")
    assert "Otomatik yedekleme başlıyor" in service_text
    assert "Otomatik yedekleme başlıyor" in gui_text
