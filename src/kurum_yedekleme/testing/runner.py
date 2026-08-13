"""TEST MODE headless tam akış çalıştırıcısı."""

from __future__ import annotations

from kurum_yedekleme.db.connection import Database
from kurum_yedekleme.db.history_repository import HistoryRepository
from kurum_yedekleme.db.models import BackupStatus
from kurum_yedekleme.services.backup_service import BackupService
from kurum_yedekleme.services.history_service import HistoryService
from kurum_yedekleme.testing.fixtures import (
    clear_test_runtime,
    generate_test_source_data,
)
from kurum_yedekleme.testing.test_mode import (
    TestModePaths,
    build_test_settings,
    resolve_test_paths,
    validate_test_settings,
)
from kurum_yedekleme.utils.logging_setup import setup_logging
from kurum_yedekleme.utils.paths import get_project_root


def run_test_mode_backup(
    *,
    project_root=None,
    force_regenerate: bool = True,
    also_console: bool = True,
) -> tuple[bool, str]:
    """
    Kaynak → ZIP → SHA-256 → test_server → SQLite → log.

    Returns:
        (ok, rapor_metni)
    """
    root = project_root or get_project_root()
    paths: TestModePaths = resolve_test_paths(root)
    stats = generate_test_source_data(paths, force=force_regenerate)
    clear_test_runtime(paths)

    settings = build_test_settings(root)
    validate_test_settings(settings, paths)
    setup_logging(paths.logs, settings.logging, also_console=also_console)

    db = Database(paths.data / "kurum_yedekleme.db")
    db.connect()
    db.initialize()
    history = HistoryService(HistoryRepository(db))
    service = BackupService(settings, history_service=history, test_mode=True)

    header = (
        "TEST MODE\n"
        f"Kaynak: {paths.source}\n"
        f"Temp: {paths.temp}\n"
        f"Test sunucu: {paths.test_server}\n"
        f"Dosya sayısı: {stats['file_count']}\n"
    )

    try:
        result = service.run_backup(
            source=paths.source,
            temp_dir=paths.temp,
            destination=paths.test_server,
            transfer=True,
            trigger="manual",
        )
        report = header + "\n" + result.format_report()
        last = history.get_last_backup()
        ok = bool(
            result.success
            and result.remote_path is not None
            and result.remote_path.is_file()
            and result.local_sha256
            and result.local_sha256 == result.remote_sha256
            and last is not None
            and last.status == BackupStatus.SUCCESS
            and not list(paths.test_server.rglob("*.tmp"))
            and not list(paths.temp.rglob("*.partial"))
        )
        return ok, report
    finally:
        db.close()
