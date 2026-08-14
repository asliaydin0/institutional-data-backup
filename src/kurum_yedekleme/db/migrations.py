"""SQLite migration / init mekanizması."""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from kurum_yedekleme.db.errors import DatabaseError

logger = logging.getLogger(__name__)

CURRENT_SCHEMA_VERSION = 3

MigrationFn = Callable[[sqlite3.Connection], None]


def _migration_001_baseline(conn: sqlite3.Connection) -> None:
    """İlk şema: meta, ayarlar, olaylar."""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS schema_meta (
            key   TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS settings (
            key        TEXT PRIMARY KEY,
            value      TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS app_events (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            level      TEXT NOT NULL,
            component  TEXT NOT NULL,
            message    TEXT NOT NULL,
            run_id     INTEGER
        );

        CREATE INDEX IF NOT EXISTS idx_app_events_created
            ON app_events(created_at DESC);
        """
    )


def _migration_002_backup_history(conn: sqlite3.Connection) -> None:
    """Eski yedekleme geçmişi (v3'te dönüştürülür)."""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS backup_history (
            id                 INTEGER PRIMARY KEY AUTOINCREMENT,
            backup_start_time  TEXT NOT NULL,
            backup_end_time    TEXT,
            source_path        TEXT NOT NULL,
            destination_path   TEXT,
            file_count         INTEGER NOT NULL DEFAULT 0,
            original_size      INTEGER NOT NULL DEFAULT 0,
            compressed_size    INTEGER NOT NULL DEFAULT 0,
            compression_ratio  REAL NOT NULL DEFAULT 0,
            sha256             TEXT,
            status             TEXT NOT NULL,
            error_message      TEXT,
            retry_count        INTEGER NOT NULL DEFAULT 0,
            CHECK (status IN ('RUNNING', 'SUCCESS', 'FAILED', 'CANCELLED'))
        );

        CREATE INDEX IF NOT EXISTS idx_backup_history_start
            ON backup_history(backup_start_time DESC);
        """
    )


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    try:
        rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    except sqlite3.Error:
        return set()
    return {str(row[1]) for row in rows}


def _duration_seconds(start: str | None, end: str | None) -> float | None:
    if not start or not end:
        return None
    try:
        started = datetime.fromisoformat(start.replace("Z", "+00:00"))
        finished = datetime.fromisoformat(end.replace("Z", "+00:00"))
        return max(0.0, (finished - started).total_seconds())
    except ValueError:
        return None


def _migration_003_areas_and_history(conn: sqlite3.Connection) -> None:
    """Alan tablosu + geçmiş şeması (area_id, backup_type; SHA yok)."""
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS backup_areas (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            name         TEXT NOT NULL,
            source_path  TEXT NOT NULL,
            enabled      INTEGER NOT NULL DEFAULT 1,
            deleted      INTEGER NOT NULL DEFAULT 0,
            created_at   TEXT NOT NULL,
            updated_at   TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_backup_areas_alive
            ON backup_areas(deleted, enabled);
        """
    )
    conn.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_backup_areas_name_alive
        ON backup_areas(name COLLATE NOCASE)
        WHERE deleted = 0
        """
    )

    old_cols = _table_columns(conn, "backup_history")
    conn.execute("DROP TABLE IF EXISTS backup_history_v3")
    conn.executescript(
        """
        CREATE TABLE backup_history_v3 (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            area_id           INTEGER,
            area_name         TEXT NOT NULL,
            backup_type       TEXT NOT NULL,
            started_at        TEXT NOT NULL,
            completed_at      TEXT,
            duration_seconds  REAL,
            backup_file       TEXT,
            file_size         INTEGER NOT NULL DEFAULT 0,
            file_count        INTEGER NOT NULL DEFAULT 0,
            status            TEXT NOT NULL,
            error_message     TEXT,
            CHECK (backup_type IN ('MANUAL', 'AUTOMATIC')),
            CHECK (status IN ('RUNNING', 'SUCCESS', 'FAILED', 'CANCELLED')),
            FOREIGN KEY (area_id) REFERENCES backup_areas(id)
        );
        """
    )

    if "source_path" in old_cols:
        rows = conn.execute("SELECT * FROM backup_history").fetchall()
        for row in rows:
            mapping = {k: row[k] for k in row.keys()}
            source = str(mapping.get("source_path") or "")
            area_name = Path(source).name if source else "Bilinmeyen alan"
            start = mapping.get("backup_start_time")
            end = mapping.get("backup_end_time")
            conn.execute(
                """
                INSERT INTO backup_history_v3 (
                    id, area_id, area_name, backup_type, started_at, completed_at,
                    duration_seconds, backup_file, file_size, file_count,
                    status, error_message
                ) VALUES (?, NULL, ?, 'MANUAL', ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    mapping.get("id"),
                    area_name,
                    start,
                    end,
                    _duration_seconds(start, end),
                    mapping.get("destination_path"),
                    int(mapping.get("compressed_size") or 0),
                    int(mapping.get("file_count") or 0),
                    mapping.get("status") or "FAILED",
                    mapping.get("error_message"),
                ),
            )
    elif "area_id" in old_cols and "backup_type" in old_cols:
        conn.execute(
            """
            INSERT INTO backup_history_v3 (
                id, area_id, area_name, backup_type, started_at, completed_at,
                duration_seconds, backup_file, file_size, file_count,
                status, error_message
            )
            SELECT
                id, area_id, area_name, backup_type, started_at, completed_at,
                duration_seconds, backup_file, file_size, file_count,
                status, error_message
            FROM backup_history
            """
        )

    conn.execute("DROP TABLE IF EXISTS backup_history")
    conn.execute("ALTER TABLE backup_history_v3 RENAME TO backup_history")
    conn.executescript(
        """
        CREATE INDEX IF NOT EXISTS idx_backup_history_started
            ON backup_history(started_at DESC);
        CREATE INDEX IF NOT EXISTS idx_backup_history_area
            ON backup_history(area_id, started_at DESC);
        CREATE INDEX IF NOT EXISTS idx_backup_history_type_status
            ON backup_history(backup_type, status);
        """
    )
    logger.info("Migration v3 uygulandı (backup_areas + yeni history) @ %s", now)


MIGRATIONS: dict[int, MigrationFn] = {
    1: _migration_001_baseline,
    2: _migration_002_backup_history,
    3: _migration_003_areas_and_history,
}


def get_schema_version(conn: sqlite3.Connection) -> int:
    try:
        row = conn.execute(
            "SELECT value FROM schema_meta WHERE key = 'version'"
        ).fetchone()
    except sqlite3.Error:
        return 0
    if row is None:
        return 0
    try:
        return int(row[0] if not hasattr(row, "keys") else row["value"])
    except (TypeError, ValueError):
        return 0


def set_schema_version(conn: sqlite3.Connection, version: int) -> None:
    conn.execute(
        """
        INSERT INTO schema_meta(key, value) VALUES('version', ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """,
        (str(version),),
    )


def run_migrations(conn: sqlite3.Connection) -> int:
    current = 0
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_meta (
                key   TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )
        current = get_schema_version(conn)
    except sqlite3.Error as exc:
        raise DatabaseError("schema_meta hazırlanamadı.") from exc

    if current > CURRENT_SCHEMA_VERSION:
        raise DatabaseError(
            f"Veritabanı şema sürümü daha yeni ({current} > {CURRENT_SCHEMA_VERSION})."
        )

    for version in range(current + 1, CURRENT_SCHEMA_VERSION + 1):
        migration = MIGRATIONS.get(version)
        if migration is None:
            raise DatabaseError(f"Migration eksik: v{version}")
        logger.info("Migration uygulanıyor: v%s", version)
        try:
            migration(conn)
            set_schema_version(conn, version)
            conn.commit()
        except sqlite3.Error as exc:
            conn.rollback()
            raise DatabaseError(f"Migration v{version} başarısız.") from exc

    final = get_schema_version(conn)
    logger.info("Veritabanı migration tamam: sürüm=%s", final)
    return final
