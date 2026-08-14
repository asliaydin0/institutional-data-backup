from __future__ import annotations

from pathlib import Path

from kurum_yedekleme.db.connection import Database
from kurum_yedekleme.db.migrations import CURRENT_SCHEMA_VERSION
from kurum_yedekleme.db.models import BackupStatus
from kurum_yedekleme.services.disk_space import is_e_drive, validate_production_backup_root
from kurum_yedekleme.services.config_validation import validate_production_settings
from kurum_yedekleme.config.schema import AppSettings, DEFAULT_BACKUP_ROOT


def test_fresh_db_schema_v3(tmp_path: Path):
    db = Database(tmp_path / "t.db")
    db.connect()
    db.initialize()
    assert db.schema_version == CURRENT_SCHEMA_VERSION
    cols = {
        row[1]
        for row in db.connect().execute("PRAGMA table_info(backup_history)").fetchall()
    }
    assert "area_id" in cols
    assert "backup_type" in cols
    assert "sha256" not in cols
    area_cols = {
        row[1]
        for row in db.connect().execute("PRAGMA table_info(backup_areas)").fetchall()
    }
    assert {"id", "name", "source_path", "enabled", "deleted"} <= area_cols
    db.close()


def test_migrates_old_history(tmp_path: Path):
    import sqlite3

    path = tmp_path / "old.db"
    conn = sqlite3.connect(str(path))
    conn.executescript(
        """
        CREATE TABLE schema_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        INSERT INTO schema_meta VALUES ('version', '2');
        CREATE TABLE settings (
            key TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE TABLE backup_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            backup_start_time TEXT NOT NULL,
            backup_end_time TEXT,
            source_path TEXT NOT NULL,
            destination_path TEXT,
            file_count INTEGER NOT NULL DEFAULT 0,
            original_size INTEGER NOT NULL DEFAULT 0,
            compressed_size INTEGER NOT NULL DEFAULT 0,
            compression_ratio REAL NOT NULL DEFAULT 0,
            sha256 TEXT,
            status TEXT NOT NULL,
            error_message TEXT,
            retry_count INTEGER NOT NULL DEFAULT 0
        );
        INSERT INTO backup_history (
            backup_start_time, backup_end_time, source_path, destination_path,
            compressed_size, status
        ) VALUES (
            '2026-08-01T02:00:00+00:00', '2026-08-01T02:05:00+00:00',
            'C:/Kaynak/Personel', 'E:/Yedekler/old.zip', 1234, 'SUCCESS'
        );
        """
    )
    conn.commit()
    conn.close()

    db = Database(path)
    db.connect()
    db.initialize()
    row = db.connect().execute(
        "SELECT area_name, backup_type, file_size, status FROM backup_history"
    ).fetchone()
    assert row["area_name"] == "Personel"
    assert row["backup_type"] == "MANUAL"
    assert row["file_size"] == 1234
    assert row["status"] == BackupStatus.SUCCESS.value
    sha_cols = {
        r[1] for r in db.connect().execute("PRAGMA table_info(backup_history)").fetchall()
    }
    assert "sha256" not in sha_cols
    db.close()


def test_production_config_requires_e_drive():
    settings = AppSettings(backup_root=r"C:\Yedekler")
    result = validate_production_settings(settings)
    assert result.ok is False
    settings_ok = AppSettings(backup_root=DEFAULT_BACKUP_ROOT)
    assert is_e_drive(settings_ok.backup_root)
    assert validate_production_settings(settings_ok).ok is True
