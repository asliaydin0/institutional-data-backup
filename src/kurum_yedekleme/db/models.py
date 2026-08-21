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

    @property
    def label_tr(self) -> str:
        return {
            BackupStatus.RUNNING: "Çalışıyor",
            BackupStatus.SUCCESS: "Başarılı",
            BackupStatus.FAILED: "Başarısız",
            BackupStatus.CANCELLED: "İptal",
        }[self]


class BackupType(str, Enum):
    """Yedeklemenin nasıl tetiklendiği."""

    MANUAL = "MANUAL"
    AUTOMATIC = "AUTOMATIC"

    @classmethod
    def parse(cls, value: str) -> BackupType:
        normalized = str(value).strip().upper()
        try:
            return cls(normalized)
        except ValueError as exc:
            raise ValueError(f"Geçersiz yedekleme türü: {value}") from exc

    @property
    def label_tr(self) -> str:
        return {
            BackupType.MANUAL: "Manuel",
            BackupType.AUTOMATIC: "Otomatik",
        }[self]


@dataclass(frozen=True)
class BackupArea:
    """backup_areas satırı."""

    id: Optional[int]
    name: str
    source_path: str
    enabled: bool
    auto_backup: bool
    deleted: bool
    created_at: datetime
    updated_at: datetime

    @property
    def is_active(self) -> bool:
        return self.enabled and not self.deleted


@dataclass(frozen=True)
class BackupHistoryRecord:
    """backup_history satırı (UI/servis DTO)."""

    id: Optional[int]
    area_id: Optional[int]
    area_name: str
    backup_type: BackupType
    started_at: datetime
    completed_at: Optional[datetime]
    duration_seconds: Optional[float]
    backup_file: Optional[str]
    file_size: int
    file_count: int
    status: BackupStatus
    error_message: Optional[str]

    @property
    def is_success(self) -> bool:
        return self.status == BackupStatus.SUCCESS
