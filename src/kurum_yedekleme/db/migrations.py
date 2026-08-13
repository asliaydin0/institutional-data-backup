"""SQLite migration / init mekanizması."""

from __future__ import annotations

import logging
import sqlite3
from typing import Callable

from kurum_yedekleme.db.errors import DatabaseError

logger = logging.getLogger(__name__)

# Her sürüm artışı için sıralı migration
CURRENT_SCHEMA_VERSION = 2

MigrationFn = Callable[[sqlite3.Connection], None]


def _migration_001_baseline(conn: sqlite3.Connection) -> None:
    """İlk şema: meta, ayarlar, olaylar ve eski yardımcı tablolar."""
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
    """Yedekleme geçmişi tablosu (kanonik)."""
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
        CREATE INDEX IF NOT EXISTS idx_backup_history_status
            ON backup_history(status);
        CREATE INDEX IF NOT EXISTS idx_backup_history_status_start
            ON backup_history(status, backup_start_time DESC);
        """
    )


MIGRATIONS: dict[int, MigrationFn] = {
    1: _migration_001_baseline,
    2: _migration_002_backup_history,
}


def get_schema_version(conn: sqlite3.Connection) -> int:
    """Mevcut şema sürümünü okur (yoksa 0)."""
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
    """
    Eksik migration'ları uygular.

    Returns:
        Ulaşılan şema sürümü.
    """
    # schema_meta yoksa sürüm 0 kabul edilir
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
