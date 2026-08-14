"""TEST MODE headless tam akış çalıştırıcısı."""

from __future__ import annotations

from kurum_yedekleme.db.models import BackupStatus, BackupType
from kurum_yedekleme.services.runtime import build_runtime
from kurum_yedekleme.testing.fixtures import (
    clear_test_runtime,
    generate_test_source_data,
)
from kurum_yedekleme.testing.test_mode import (
    TestModePaths,
    build_test_settings,
    resolve_test_paths,
    seed_test_areas,
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
    root = project_root or get_project_root()
    paths: TestModePaths = resolve_test_paths(root)
    stats = generate_test_source_data(paths, force=force_regenerate)
    clear_test_runtime(paths)

    settings = build_test_settings(root)
    validate_test_settings(settings, paths)
    setup_logging(paths.logs, settings.logging, also_console=also_console)

    runtime = build_runtime(settings, test_mode=True)
    seed_test_areas(runtime.areas, paths)

    header = (
        "TEST MODE\n"
        f"Kaynak: {paths.source}\n"
        f"Yedek kök: {paths.yedekler}\n"
        f"Dosya sayısı: {stats['file_count']}\n"
    )
    try:
        job = runtime.backups.run(
            runtime.areas.list_enabled(),
            backup_type=BackupType.MANUAL,
        )
        report = header + "\n" + job.format_report()
        last = runtime.history.get_last_backup()
        zips = list(paths.yedekler.rglob("*.zip"))
        tmps = list(paths.yedekler.rglob("*.tmp"))
        ok = bool(
            job.success_count >= 1
            and last is not None
            and last.status == BackupStatus.SUCCESS
            and last.backup_type == BackupType.MANUAL
            and last.area_name
            and zips
            and not tmps
        )
        return ok, report
    finally:
        runtime.close()
