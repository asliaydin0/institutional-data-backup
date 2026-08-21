"""Yedekleme alanları repository."""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timezone
from typing import Optional

from kurum_yedekleme.db.connection import Database
from kurum_yedekleme.db.errors import DatabaseError
from kurum_yedekleme.db.models import BackupArea

logger = logging.getLogger(__name__)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _to_iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat()


def _parse_dt(value: Optional[str]) -> datetime:
    if not value:
        return _utc_now()
    text = value.replace("Z", "+00:00")
    return datetime.fromisoformat(text)


def _row_to_area(row: sqlite3.Row) -> BackupArea:
    return BackupArea(
        id=int(row["id"]),
        name=str(row["name"]),
        source_path=str(row["source_path"]),
        enabled=bool(row["enabled"]),
        auto_backup=bool(row["auto_backup"]) if "auto_backup" in row.keys() else True,
        deleted=bool(row["deleted"]),
        created_at=_parse_dt(row["created_at"]),
        updated_at=_parse_dt(row["updated_at"]),
    )


class AreasRepository:
    """backup_areas CRUD — silme soft delete."""

    def __init__(self, database: Database) -> None:
        self._db = database

    def insert(
        self,
        *,
        name: str,
        source_path: str,
        enabled: bool = True,
        auto_backup: bool = True,
    ) -> BackupArea:
        now = _to_iso(_utc_now())
        conn = self._db.connect()
        try:
            cursor = conn.execute(
                """
                INSERT INTO backup_areas (
                    name, source_path, enabled, auto_backup, deleted,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, 0, ?, ?)
                """,
                (
                    name.strip(),
                    source_path.strip(),
                    1 if enabled else 0,
                    1 if auto_backup else 0,
                    now,
                    now,
                ),
            )
            conn.commit()
            area_id = int(cursor.lastrowid)
        except sqlite3.IntegrityError as exc:
            conn.rollback()
            raise DatabaseError(
                f"Bu alan adı zaten kayıtlı: {name.strip()!r}"
            ) from exc
        except sqlite3.Error as exc:
            conn.rollback()
            raise DatabaseError("Alan eklenemedi.") from exc
        area = self.get_by_id(area_id)
        if area is None:
            raise DatabaseError("Eklenen alan okunamadı.")
        logger.info("Alan eklendi id=%s name=%s", area_id, name)
        return area

    def update(
        self,
        area_id: int,
        *,
        name: str,
        source_path: str,
        enabled: bool,
        auto_backup: bool | None = None,
    ) -> BackupArea:
        now = _to_iso(_utc_now())
        current = self.get_by_id(area_id, include_deleted=False)
        if current is None:
            raise DatabaseError(f"Alan bulunamadı: id={area_id}")
        flag = current.auto_backup if auto_backup is None else bool(auto_backup)
        conn = self._db.connect()
        try:
            cursor = conn.execute(
                """
                UPDATE backup_areas
                SET name = ?, source_path = ?, enabled = ?, auto_backup = ?,
                    updated_at = ?
                WHERE id = ? AND deleted = 0
                """,
                (
                    name.strip(),
                    source_path.strip(),
                    1 if enabled else 0,
                    1 if flag else 0,
                    now,
                    area_id,
                ),
            )
            if cursor.rowcount == 0:
                raise DatabaseError(f"Alan bulunamadı: id={area_id}")
            conn.commit()
        except DatabaseError:
            conn.rollback()
            raise
        except sqlite3.IntegrityError as exc:
            conn.rollback()
            raise DatabaseError(
                f"Bu alan adı zaten kayıtlı: {name.strip()!r}"
            ) from exc
        except sqlite3.Error as exc:
            conn.rollback()
            raise DatabaseError("Alan güncellenemedi.") from exc
        area = self.get_by_id(area_id)
        if area is None:
            raise DatabaseError("Güncellenen alan okunamadı.")
        logger.info("Alan güncellendi id=%s name=%s", area_id, name)
        return area

    def set_enabled(self, area_id: int, enabled: bool) -> BackupArea:
        area = self.get_by_id(area_id, include_deleted=False)
        if area is None:
            raise DatabaseError(f"Alan bulunamadı: id={area_id}")
        return self.update(
            area_id,
            name=area.name,
            source_path=area.source_path,
            enabled=enabled,
        )

    def soft_delete(self, area_id: int) -> None:
        now = _to_iso(_utc_now())
        conn = self._db.connect()
        try:
            cursor = conn.execute(
                """
                UPDATE backup_areas
                SET deleted = 1, enabled = 0, updated_at = ?
                WHERE id = ? AND deleted = 0
                """,
                (now, area_id),
            )
            if cursor.rowcount == 0:
                raise DatabaseError(f"Alan bulunamadı: id={area_id}")
            conn.commit()
        except DatabaseError:
            conn.rollback()
            raise
        except sqlite3.Error as exc:
            conn.rollback()
            raise DatabaseError("Alan kaldırılamadı.") from exc
        logger.info("Alan soft-delete id=%s", area_id)

    def get_by_id(
        self, area_id: int, *, include_deleted: bool = True
    ) -> Optional[BackupArea]:
        conn = self._db.connect()
        sql = "SELECT * FROM backup_areas WHERE id = ?"
        params: list[object] = [area_id]
        if not include_deleted:
            sql += " AND deleted = 0"
        row = conn.execute(sql, params).fetchone()
        return _row_to_area(row) if row else None

    def get_by_name(
        self, name: str, *, include_deleted: bool = False
    ) -> Optional[BackupArea]:
        conn = self._db.connect()
        sql = "SELECT * FROM backup_areas WHERE name = ? COLLATE NOCASE"
        params: list[object] = [name.strip()]
        if not include_deleted:
            sql += " AND deleted = 0"
        row = conn.execute(sql, params).fetchone()
        return _row_to_area(row) if row else None

    def list_alive(self) -> list[BackupArea]:
        conn = self._db.connect()
        rows = conn.execute(
            """
            SELECT * FROM backup_areas
            WHERE deleted = 0
            ORDER BY name COLLATE NOCASE
            """
        ).fetchall()
        return [_row_to_area(row) for row in rows]

    def set_auto_backup(self, area_id: int, auto_backup: bool) -> BackupArea:
        area = self.get_by_id(area_id, include_deleted=False)
        if area is None:
            raise DatabaseError(f"Alan bulunamadı: id={area_id}")
        return self.update(
            area_id,
            name=area.name,
            source_path=area.source_path,
            enabled=area.enabled,
            auto_backup=auto_backup,
        )

    def list_for_automatic(self) -> list[BackupArea]:
        conn = self._db.connect()
        rows = conn.execute(
            """
            SELECT * FROM backup_areas
            WHERE deleted = 0 AND enabled = 1 AND auto_backup = 1
            ORDER BY name COLLATE NOCASE
            """
        ).fetchall()
        return [_row_to_area(row) for row in rows]

    def list_enabled(self) -> list[BackupArea]:
        conn = self._db.connect()
        rows = conn.execute(
            """
            SELECT * FROM backup_areas
            WHERE deleted = 0 AND enabled = 1
            ORDER BY name COLLATE NOCASE
            """
        ).fetchall()
        return [_row_to_area(row) for row in rows]
