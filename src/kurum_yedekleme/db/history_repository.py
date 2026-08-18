"""Yedekleme geçmişi repository."""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timezone
from typing import Any, Optional

from kurum_yedekleme.db.connection import Database
from kurum_yedekleme.db.errors import DatabaseError
from kurum_yedekleme.db.models import BackupHistoryRecord, BackupStatus, BackupType

logger = logging.getLogger(__name__)

_SELECT_COLUMNS = """
    id,
    area_id,
    area_name,
    backup_type,
    started_at,
    completed_at,
    duration_seconds,
    backup_file,
    file_size,
    file_count,
    status,
    error_message
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
    area_id_raw = row["area_id"]
    return BackupHistoryRecord(
        id=int(row["id"]),
        area_id=int(area_id_raw) if area_id_raw is not None else None,
        area_name=str(row["area_name"]),
        backup_type=BackupType.parse(str(row["backup_type"])),
        started_at=_parse_dt(row["started_at"]) or datetime.now(timezone.utc),
        completed_at=_parse_dt(row["completed_at"]),
        duration_seconds=(
            float(row["duration_seconds"])
            if row["duration_seconds"] is not None
            else None
        ),
        backup_file=row["backup_file"],
        file_size=int(row["file_size"] or 0),
        file_count=int(row["file_count"] or 0),
        status=BackupStatus.parse(str(row["status"])),
        error_message=row["error_message"],
    )


class HistoryRepository:
    """backup_history CRUD / sorgu katmanı."""

    def __init__(self, database: Database) -> None:
        self._db = database

    def insert_running(
        self,
        *,
        area_id: Optional[int],
        area_name: str,
        backup_type: BackupType,
        start_time: Optional[datetime] = None,
    ) -> int:
        started = start_time or datetime.now(timezone.utc)
        conn = self._db.connect()
        try:
            cursor = conn.execute(
                """
                INSERT INTO backup_history (
                    area_id, area_name, backup_type, started_at, completed_at,
                    duration_seconds, backup_file, file_size, file_count,
                    status, error_message
                ) VALUES (?, ?, ?, ?, NULL, NULL, NULL, 0, 0, ?, NULL)
                """,
                (
                    area_id,
                    area_name,
                    backup_type.value,
                    _to_iso(started),
                    BackupStatus.RUNNING.value,
                ),
            )
            conn.commit()
            record_id = int(cursor.lastrowid)
            logger.info(
                "Geçmiş RUNNING id=%s alan=%s tür=%s",
                record_id,
                area_name,
                backup_type.value,
            )
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
        backup_file: Optional[str] = None,
        file_size: int = 0,
        file_count: int = 0,
        error_message: Optional[str] = None,
        duration_seconds: Optional[float] = None,
    ) -> None:
        if status == BackupStatus.RUNNING:
            raise DatabaseError("update_finished RUNNING ile çağrılamaz.")
        finished = end_time or datetime.now(timezone.utc)
        conn = self._db.connect()
        try:
            cursor = conn.execute(
                """
                UPDATE backup_history SET
                    completed_at = ?,
                    duration_seconds = ?,
                    backup_file = COALESCE(?, backup_file),
                    file_size = ?,
                    file_count = ?,
                    status = ?,
                    error_message = ?
                WHERE id = ?
                """,
                (
                    _to_iso(finished),
                    duration_seconds,
                    backup_file,
                    file_size,
                    file_count,
                    status.value,
                    error_message,
                    record_id,
                ),
            )
            if cursor.rowcount == 0:
                raise DatabaseError(f"Geçmiş kaydı bulunamadı: id={record_id}")
            conn.commit()
            logger.info(
                "Geçmiş güncellendi id=%s status=%s",
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
            ORDER BY started_at DESC, id DESC
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
            ORDER BY started_at DESC, id DESC
            LIMIT 1
            """,
            (status.value,),
        ).fetchone()
        return _row_to_record(row) if row else None

    def fetch_last_by_type(
        self, backup_type: BackupType
    ) -> Optional[BackupHistoryRecord]:
        conn = self._db.connect()
        row = conn.execute(
            f"""
            SELECT {_SELECT_COLUMNS}
            FROM backup_history
            WHERE backup_type = ?
            ORDER BY started_at DESC, id DESC
            LIMIT 1
            """,
            (backup_type.value,),
        ).fetchone()
        return _row_to_record(row) if row else None

    def fetch_last_for_area(self, area_id: int) -> Optional[BackupHistoryRecord]:
        conn = self._db.connect()
        row = conn.execute(
            f"""
            SELECT {_SELECT_COLUMNS}
            FROM backup_history
            WHERE area_id = ?
            ORDER BY started_at DESC, id DESC
            LIMIT 1
            """,
            (area_id,),
        ).fetchone()
        return _row_to_record(row) if row else None

    def fail_stale_running(
        self,
        *,
        error_message: str = (
            "Uygulama beklenmedik şekilde kapandı; yedekleme tamamlanmadı."
        ),
    ) -> int:
        """Açılışta yarım kalmış RUNNING kayıtlarını FAILED yapar."""
        conn = self._db.connect()
        finished = _to_iso(datetime.now(timezone.utc))
        try:
            cursor = conn.execute(
                """
                UPDATE backup_history SET
                    status = ?,
                    completed_at = ?,
                    error_message = ?
                WHERE status = ?
                """,
                (
                    BackupStatus.FAILED.value,
                    finished,
                    error_message,
                    BackupStatus.RUNNING.value,
                ),
            )
            conn.commit()
            count = int(cursor.rowcount)
            if count:
                logger.warning(
                    "Yarım kalmış %s RUNNING kaydı FAILED olarak işaretlendi",
                    count,
                )
            return count
        except sqlite3.Error as exc:
            conn.rollback()
            raise DatabaseError("Yarım RUNNING kayıtları güncellenemedi.") from exc

    def fetch_filtered(
        self,
        *,
        area_id: Optional[int] = None,
        backup_type: Optional[BackupType] = None,
        status: Optional[BackupStatus] = None,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        limit: int = 500,
    ) -> list[BackupHistoryRecord]:
        clauses: list[str] = []
        params: list[Any] = []
        if area_id is not None:
            clauses.append("area_id = ?")
            params.append(area_id)
        if backup_type is not None:
            clauses.append("backup_type = ?")
            params.append(backup_type.value)
        if status is not None:
            clauses.append("status = ?")
            params.append(status.value)
        if start is not None:
            clauses.append("started_at >= ?")
            params.append(_to_iso(start))
        if end is not None:
            clauses.append("started_at <= ?")
            params.append(_to_iso(end))
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        sql = f"""
            SELECT {_SELECT_COLUMNS}
            FROM backup_history
            {where}
            ORDER BY started_at DESC, id DESC
            LIMIT ?
        """
        params.append(max(1, int(limit)))
        conn = self._db.connect()
        rows = conn.execute(sql, params).fetchall()
        return [_row_to_record(row) for row in rows]

    def fetch_today(self, today_iso_prefix: str) -> list[BackupHistoryRecord]:
        conn = self._db.connect()
        rows = conn.execute(
            f"""
            SELECT {_SELECT_COLUMNS}
            FROM backup_history
            WHERE started_at LIKE ? || '%'
               OR started_at LIKE ? || '%'
            ORDER BY started_at DESC, id DESC
            """,
            (today_iso_prefix, f"{today_iso_prefix}T"),
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
