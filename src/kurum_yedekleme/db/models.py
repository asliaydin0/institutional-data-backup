"""Veritabanı modelleri ve durum sabitleri."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional


class BackupStatus(str, Enum):
    """Kontrollü yedekleme durumları."""

    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"

    @classmethod
    def parse(cls, value: str) -> BackupStatus:
        normalized = str(value).strip().upper()
        try:
            return cls(normalized)
        except ValueError as exc:
            raise ValueError(f"Geçersiz yedekleme durumu: {value}") from exc


TRIGGER_MANUAL = "manual"
TRIGGER_SCHEDULE = "schedule"


@dataclass(frozen=True)
class BackupHistoryRecord:
    """backup_history satırı (UI/servis DTO)."""

    id: Optional[int]
    backup_start_time: datetime
    backup_end_time: Optional[datetime]
    source_path: str
    destination_path: Optional[str]
    file_count: int
    original_size: int
    compressed_size: int
    compression_ratio: float
    sha256: Optional[str]
    status: BackupStatus
    error_message: Optional[str]
    retry_count: int

    @property
    def is_success(self) -> bool:
        return self.status == BackupStatus.SUCCESS
