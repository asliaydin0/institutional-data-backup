"""Yedekleme geçmişi servisi — GUI ve üst katmanlar yalnızca burayı kullanır."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from kurum_yedekleme.core.backup_engine import BackupResult
from kurum_yedekleme.db.history_repository import HistoryRepository
from kurum_yedekleme.db.models import BackupHistoryRecord, BackupStatus

logger = logging.getLogger(__name__)


class HistoryService:
    """
    Yedekleme geçmişi iş kuralları.

    UI katmanı SQLite sorgusu çalıştırmaz; bu servisi kullanır.
    """

    def __init__(self, repository: HistoryRepository) -> None:
        self._repo = repository

    def start_run(
        self,
        *,
        source_path: str,
        destination_path: Optional[str] = None,
        start_time: Optional[datetime] = None,
    ) -> int:
        """Yedekleme başlangıcını RUNNING olarak kaydeder."""
        record_id = self._repo.insert_running(
            source_path=source_path,
            destination_path=destination_path,
            start_time=start_time,
        )
        logger.info("Geçmiş: RUNNING id=%s kaynak=%s", record_id, source_path)
        return record_id

    def complete_from_result(
        self,
        record_id: int,
        result: BackupResult,
    ) -> BackupHistoryRecord:
        """BackupResult'a göre kaydı SUCCESS veya FAILED yapar."""
        status = BackupStatus.SUCCESS if result.success else BackupStatus.FAILED
        destination = None
        if result.remote_path is not None:
            destination = str(result.remote_path)
        elif result.zip_path is not None:
            destination = str(result.zip_path)

        error_message = None
        if not result.success:
            error_message = result.transfer_message or result.message or "Başarısız"
        elif result.error_files:
            error_message = f"{len(result.error_files)} dosyada uyarı"

        self._repo.update_finished(
            record_id,
            status=status,
            end_time=result.finished_at,
            destination_path=destination,
            file_count=result.file_count,
            original_size=result.original_size,
            compressed_size=result.zip_size,
            compression_ratio=float(result.compression_ratio_percent),
            sha256=result.local_sha256 or result.remote_sha256,
            error_message=error_message,
            retry_count=int(result.transfer_attempts or 0),
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
        retry_count: int = 0,
    ) -> None:
        """Beklenmeyen hata durumunda FAILED işaretler."""
        self._repo.update_finished(
            record_id,
            status=BackupStatus.FAILED,
            end_time=end_time,
            error_message=error_message,
            retry_count=retry_count,
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
        """Son başarılı yedekleme."""
        return self._repo.fetch_last_by_status(BackupStatus.SUCCESS)

    def get_last_backup(self) -> Optional[BackupHistoryRecord]:
        """Son yedekleme (durumdan bağımsız)."""
        return self._repo.fetch_last()

    def get_last_n(self, limit: int = 10) -> list[BackupHistoryRecord]:
        """Son N yedekleme (varsayılan 10)."""
        return self._repo.fetch_recent(limit=limit)

    def get_failed_backups(
        self, *, limit: Optional[int] = None
    ) -> list[BackupHistoryRecord]:
        """Başarısız yedeklemeler."""
        return self._repo.fetch_by_status(BackupStatus.FAILED, limit=limit)

    def get_backups_in_range(
        self, start: datetime, end: datetime
    ) -> list[BackupHistoryRecord]:
        """Belirli tarih aralığındaki yedeklemeler."""
        return self._repo.fetch_by_date_range(start, end)

    def count_successful(self) -> int:
        """Toplam başarılı yedekleme sayısı."""
        return self._repo.count_by_status(BackupStatus.SUCCESS)

    def count_all(self) -> int:
        """Toplam kayıt sayısı."""
        return self._repo.count_all()

    # Geriye dönük uyumluluk
    def get_run_count(self) -> int:
        return self.count_all()
