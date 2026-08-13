"""Yedekleme geçmişi repository — yalnızca SQL erişimi."""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timezone
from typing import Any, Optional

from kurum_yedekleme.db.connection import Database
from kurum_yedekleme.db.errors import DatabaseError
from kurum_yedekleme.db.models import BackupHistoryRecord, BackupStatus

logger = logging.getLogger(__name__)

_SELECT_COLUMNS = """
    id,
    backup_start_time,
    backup_end_time,
    source_path,
    destination_path,
    file_count,
    original_size,
    compressed_size,
    compression_ratio,
    sha256,
    status,
    error_message,
    retry_count
"""


def _to_iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat()


def _parse_dt(value: Optional[str]) -> Optional[datetime]:
    if value is None or value == "":
        return None
    text = value.replace("Z", "+00:00")
    return datetime.fromisoformat(text)


def _row_to_record(row: sqlite3.Row) -> BackupHistoryRecord:
    return BackupHistoryRecord(
        id=int(row["id"]),
        backup_start_time=_parse_dt(row["backup_start_time"])  # type: ignore[arg-type]
        or datetime.now(timezone.utc),
        backup_end_time=_parse_dt(row["backup_end_time"]),
        source_path=str(row["source_path"]),
        destination_path=row["destination_path"],
        file_count=int(row["file_count"] or 0),
        original_size=int(row["original_size"] or 0),
        compressed_size=int(row["compressed_size"] or 0),
        compression_ratio=float(row["compression_ratio"] or 0.0),
        sha256=row["sha256"],
        status=BackupStatus.parse(str(row["status"])),
        error_message=row["error_message"],
        retry_count=int(row["retry_count"] or 0),
    )


class HistoryRepository:
    """backup_history tablosu için CRUD / sorgu katmanı."""

    def __init__(self, database: Database) -> None:
        self._db = database

    def insert_running(
        self,
        *,
        source_path: str,
        destination_path: Optional[str],
        start_time: Optional[datetime] = None,
    ) -> int:
        """RUNNING durumunda yeni kayıt ekler; id döner."""
        started = start_time or datetime.now(timezone.utc)
        conn = self._db.connect()
        try:
            cursor = conn.execute(
                """
                INSERT INTO backup_history (
                    backup_start_time,
                    backup_end_time,
                    source_path,
                    destination_path,
                    file_count,
                    original_size,
                    compressed_size,
                    compression_ratio,
                    sha256,
                    status,
                    error_message,
                    retry_count
                ) VALUES (?, NULL, ?, ?, 0, 0, 0, 0, NULL, ?, NULL, 0)
                """,
                (
                    _to_iso(started),
                    source_path,
                    destination_path,
                    BackupStatus.RUNNING.value,
                ),
            )
            conn.commit()
            record_id = int(cursor.lastrowid)
            logger.info("Geçmiş kaydı oluşturuldu id=%s status=RUNNING", record_id)
            return record_id
        except sqlite3.Error as exc:
            conn.rollback()
            raise DatabaseError("RUNNING kaydı eklenemedi.") from exc

    def update_finished(
        self,
        record_id: int,
        *,
        status: BackupStatus,
        end_time: Optional[datetime] = None,
        destination_path: Optional[str] = None,
        file_count: int = 0,
        original_size: int = 0,
        compressed_size: int = 0,
        compression_ratio: float = 0.0,
        sha256: Optional[str] = None,
        error_message: Optional[str] = None,
        retry_count: int = 0,
    ) -> None:
        """Kaydı tamamlar / günceller."""
        if status == BackupStatus.RUNNING:
            raise DatabaseError("update_finished RUNNING ile çağrılamaz.")
        finished = end_time or datetime.now(timezone.utc)
        conn = self._db.connect()
        try:
            cursor = conn.execute(
                """
                UPDATE backup_history SET
                    backup_end_time = ?,
                    destination_path = COALESCE(?, destination_path),
                    file_count = ?,
                    original_size = ?,
                    compressed_size = ?,
                    compression_ratio = ?,
                    sha256 = ?,
                    status = ?,
                    error_message = ?,
                    retry_count = ?
                WHERE id = ?
                """,
                (
                    _to_iso(finished),
                    destination_path,
                    file_count,
                    original_size,
                    compressed_size,
                    compression_ratio,
                    sha256,
                    status.value,
                    error_message,
                    retry_count,
                    record_id,
                ),
            )
            if cursor.rowcount == 0:
                raise DatabaseError(f"Geçmiş kaydı bulunamadı: id={record_id}")
            conn.commit()
            logger.info(
                "Geçmiş kaydı güncellendi id=%s status=%s",
                record_id,
                status.value,
            )
        except DatabaseError:
            conn.rollback()
            raise
        except sqlite3.Error as exc:
            conn.rollback()
            raise DatabaseError("Geçmiş kaydı güncellenemedi.") from exc

    def get_by_id(self, record_id: int) -> Optional[BackupHistoryRecord]:
        conn = self._db.connect()
        row = conn.execute(
            f"SELECT {_SELECT_COLUMNS} FROM backup_history WHERE id = ?",
            (record_id,),
        ).fetchone()
        return _row_to_record(row) if row else None

    def fetch_recent(self, limit: int = 10) -> list[BackupHistoryRecord]:
        limit = max(1, int(limit))
        conn = self._db.connect()
        rows = conn.execute(
            f"""
            SELECT {_SELECT_COLUMNS}
            FROM backup_history
            ORDER BY backup_start_time DESC, id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [_row_to_record(row) for row in rows]

    def fetch_last(self) -> Optional[BackupHistoryRecord]:
        rows = self.fetch_recent(1)
        return rows[0] if rows else None

    def fetch_last_by_status(
        self, status: BackupStatus
    ) -> Optional[BackupHistoryRecord]:
        conn = self._db.connect()
        row = conn.execute(
            f"""
            SELECT {_SELECT_COLUMNS}
            FROM backup_history
            WHERE status = ?
            ORDER BY backup_start_time DESC, id DESC
            LIMIT 1
            """,
            (status.value,),
        ).fetchone()
        return _row_to_record(row) if row else None

    def fetch_by_status(
        self, status: BackupStatus, *, limit: Optional[int] = None
    ) -> list[BackupHistoryRecord]:
        conn = self._db.connect()
        sql = f"""
            SELECT {_SELECT_COLUMNS}
            FROM backup_history
            WHERE status = ?
            ORDER BY backup_start_time DESC, id DESC
        """
        params: list[Any] = [status.value]
        if limit is not None:
            sql += " LIMIT ?"
            params.append(max(1, int(limit)))
        rows = conn.execute(sql, params).fetchall()
        return [_row_to_record(row) for row in rows]

    def fetch_by_date_range(
        self,
        start: datetime,
        end: datetime,
    ) -> list[BackupHistoryRecord]:
        if end < start:
            raise DatabaseError("Bitiş tarihi başlangıçtan önce olamaz.")
        conn = self._db.connect()
        rows = conn.execute(
            f"""
            SELECT {_SELECT_COLUMNS}
            FROM backup_history
            WHERE backup_start_time >= ?
              AND backup_start_time <= ?
            ORDER BY backup_start_time DESC, id DESC
            """,
            (_to_iso(start), _to_iso(end)),
        ).fetchall()
        return [_row_to_record(row) for row in rows]

    def count_by_status(self, status: BackupStatus) -> int:
        conn = self._db.connect()
        row = conn.execute(
            "SELECT COUNT(*) AS c FROM backup_history WHERE status = ?",
            (status.value,),
        ).fetchone()
        return int(row["c"]) if row else 0

    def count_all(self) -> int:
        conn = self._db.connect()
        row = conn.execute("SELECT COUNT(*) AS c FROM backup_history").fetchone()
        return int(row["c"]) if row else 0
