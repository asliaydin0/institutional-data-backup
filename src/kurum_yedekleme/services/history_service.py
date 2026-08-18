"""Yedekleme geçmişi servisi — GUI ve üst katmanlar yalnızca burayı kullanır."""

from __future__ import annotations

import logging
from datetime import datetime, time, timedelta
from typing import Optional

from kurum_yedekleme.config.periodic import period_bounds_utc

from kurum_yedekleme.core.backup_engine import AreaBackupResult
from kurum_yedekleme.db.history_repository import HistoryRepository
from kurum_yedekleme.db.models import (
    BackupHistoryRecord,
    BackupStatus,
    BackupType,
)

logger = logging.getLogger(__name__)


class HistoryService:
    def __init__(self, repository: HistoryRepository) -> None:
        self._repo = repository

    def recover_stale_running_on_startup(self) -> int:
        """Önceki çökme/kill sonrası RUNNING kalan kayıtları FAILED yapar."""
        return self._repo.fail_stale_running()

    def start_run(
        self,
        *,
        area_id: Optional[int],
        area_name: str,
        backup_type: BackupType,
        start_time: Optional[datetime] = None,
    ) -> int:
        return self._repo.insert_running(
            area_id=area_id,
            area_name=area_name,
            backup_type=backup_type,
            start_time=start_time,
        )

    def complete_from_result(
        self,
        record_id: int,
        result: AreaBackupResult,
    ) -> BackupHistoryRecord:
        error_message = None
        if not result.success:
            error_message = result.message or "Başarısız"

        self._repo.update_finished(
            record_id,
            status=result.status,
            end_time=result.finished_at,
            backup_file=str(result.zip_path) if result.zip_path else None,
            file_size=result.zip_size,
            file_count=result.file_count,
            error_message=error_message,
            duration_seconds=result.duration_seconds,
        )
        record = self._repo.get_by_id(record_id)
        if record is None:
            raise RuntimeError(f"Güncellenen kayıt okunamadı: {record_id}")
        return record

    def mark_failed(
        self,
        record_id: int,
        *,
        error_message: str,
        end_time: Optional[datetime] = None,
    ) -> None:
        self._repo.update_finished(
            record_id,
            status=BackupStatus.FAILED,
            end_time=end_time,
            error_message=error_message,
        )

    def mark_cancelled(
        self,
        record_id: int,
        *,
        error_message: str = "Kullanıcı tarafından iptal edildi",
        end_time: Optional[datetime] = None,
    ) -> None:
        self._repo.update_finished(
            record_id,
            status=BackupStatus.CANCELLED,
            end_time=end_time,
            error_message=error_message,
        )

    def get_last_successful(self) -> Optional[BackupHistoryRecord]:
        return self._repo.fetch_last_by_status(BackupStatus.SUCCESS)

    def get_last_backup(self) -> Optional[BackupHistoryRecord]:
        return self._repo.fetch_last()

    def get_last_n(self, limit: int = 10) -> list[BackupHistoryRecord]:
        return self._repo.fetch_recent(limit=limit)

    def get_last_by_type(
        self, backup_type: BackupType
    ) -> Optional[BackupHistoryRecord]:
        return self._repo.fetch_last_by_type(backup_type)

    def get_last_for_area(self, area_id: int) -> Optional[BackupHistoryRecord]:
        return self._repo.fetch_last_for_area(area_id)

    def get_failed_backups(
        self, *, limit: Optional[int] = None
    ) -> list[BackupHistoryRecord]:
        return self._repo.fetch_filtered(
            status=BackupStatus.FAILED, limit=limit or 50
        )

    def filter(
        self,
        *,
        area_id: Optional[int] = None,
        backup_type: Optional[BackupType] = None,
        status: Optional[BackupStatus] = None,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        limit: int = 500,
    ) -> list[BackupHistoryRecord]:
        return self._repo.fetch_filtered(
            area_id=area_id,
            backup_type=backup_type,
            status=status,
            start=start,
            end=end,
            limit=limit,
        )

    def count_successful(self) -> int:
        return self._repo.count_by_status(BackupStatus.SUCCESS)

    def count_all(self) -> int:
        return self._repo.count_all()

    def has_successful_automatic_in_period(
        self,
        area_id: int,
        frequency: str,
        *,
        now: Optional[datetime] = None,
    ) -> bool:
        start, end = period_bounds_utc(now or datetime.now().astimezone(), frequency)
        rows = self._repo.fetch_filtered(
            area_id=area_id,
            backup_type=BackupType.AUTOMATIC,
            status=BackupStatus.SUCCESS,
            start=start,
            end=end,
            limit=1,
        )
        return bool(rows)

    def has_successful_automatic_today(
        self, area_id: int, *, now: Optional[datetime] = None
    ) -> bool:
        return self.has_successful_automatic_in_period(
            area_id, "daily", now=now
        )

    def today_records(
        self, *, now: Optional[datetime] = None
    ) -> list[BackupHistoryRecord]:
        start, end = local_day_bounds_utc(now)
        return self._repo.fetch_filtered(start=start, end=end, limit=1000)


def local_day_bounds_utc(
    now: Optional[datetime] = None,
) -> tuple[datetime, datetime]:
    moment = now or datetime.now().astimezone()
    if moment.tzinfo is None:
        moment = moment.astimezone()
    start_local = datetime.combine(moment.date(), time.min, tzinfo=moment.tzinfo)
    end_local = start_local + timedelta(days=1) - timedelta(seconds=1)
    return start_local.astimezone(), end_local.astimezone()
