"""GUI ve Windows Service için ortak çalışma zamanı."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from kurum_yedekleme.config.schema import AppSettings
from kurum_yedekleme.core.lock import BackupLock
from kurum_yedekleme.db.areas_repository import AreasRepository
from kurum_yedekleme.db.connection import Database
from kurum_yedekleme.db.history_repository import HistoryRepository
from kurum_yedekleme.db.repository import Repository
from kurum_yedekleme.services.area_service import AreaService
from kurum_yedekleme.services.backup_manager import BackupManager
from kurum_yedekleme.services.history_service import HistoryService
from kurum_yedekleme.services.schedule_service import ScheduleService
from kurum_yedekleme.utils.paths import resolve_under_root


@dataclass
class AppRuntime:
    settings: AppSettings
    database: Database
    areas: AreaService
    history: HistoryService
    backups: BackupManager
    schedule: ScheduleService
    lock: BackupLock
    events: Repository
    data_dir: Path
    log_dir: Path
    test_mode: bool

    def close(self) -> None:
        self.schedule.stop()
        self.database.close()


def build_runtime(
    settings: AppSettings,
    *,
    test_mode: bool = False,
    poll_interval_seconds: float = 20.0,
) -> AppRuntime:
    data_dir = resolve_under_root(settings.app.data_dir)
    log_dir = resolve_under_root(settings.app.log_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)

    database = Database(data_dir / "kurum_yedekleme.db")
    database.connect()
    database.initialize()

    areas = AreaService(AreasRepository(database))
    history = HistoryService(HistoryRepository(database))
    lock = BackupLock(data_dir / "backup.lock")
    backups = BackupManager(
        settings,
        history_service=history,
        lock=lock,
        test_mode=test_mode,
    )
    schedule = ScheduleService(
        settings.schedule,
        backups,
        areas,
        history,
        poll_interval_seconds=poll_interval_seconds,
    )
    return AppRuntime(
        settings=settings,
        database=database,
        areas=areas,
        history=history,
        backups=backups,
        schedule=schedule,
        lock=lock,
        events=Repository(database),
        data_dir=data_dir,
        log_dir=log_dir,
        test_mode=test_mode,
    )
