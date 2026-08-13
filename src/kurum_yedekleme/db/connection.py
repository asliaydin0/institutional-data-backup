"""SQLite bağlantı ve init."""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from typing import Optional

from kurum_yedekleme.db.errors import DatabaseError
from kurum_yedekleme.db.migrations import CURRENT_SCHEMA_VERSION, run_migrations

logger = logging.getLogger(__name__)

__all__ = ["Database", "DatabaseError"]

class Database:
    """SQLite bağlantı yöneticisi — ilk açılışta otomatik oluşturur."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)
        self._connection: Optional[sqlite3.Connection] = None
        self.schema_version: int = 0

    def connect(self) -> sqlite3.Connection:
        """Bağlantıyı açar (dosya yoksa oluşturur)."""
        if self._connection is not None:
            return self._connection

        try:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            created = not self.db_path.exists()
            conn = sqlite3.connect(
                str(self.db_path),
                detect_types=sqlite3.PARSE_DECLTYPES,
                check_same_thread=False,
            )
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("PRAGMA journal_mode = WAL")
            self._connection = conn
            if created:
                logger.info("Yeni SQLite veritabanı oluşturuldu: %s", self.db_path)
            else:
                logger.info("SQLite bağlantısı açıldı: %s", self.db_path)
            return conn
        except sqlite3.Error as exc:
            raise DatabaseError(
                f"Veritabanına bağlanılamadı: {self.db_path}"
            ) from exc

    def initialize(self) -> None:
        """Migration'ları çalıştırarak şemayı hazırlar; bozuk DB'yi erken yakalar."""
        conn = self.connect()
        try:
            self._assert_integrity(conn)
            self.schema_version = run_migrations(conn)
            logger.info(
                "Veritabanı hazır (hedef sürüm=%s, mevcut=%s)",
                CURRENT_SCHEMA_VERSION,
                self.schema_version,
            )
        except DatabaseError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise DatabaseError("Veritabanı başlatılamadı.") from exc

    @staticmethod
    def _assert_integrity(conn: sqlite3.Connection) -> None:
        """PRAGMA quick_check — bozulmuş dosyada anlaşılır hata."""
        try:
            row = conn.execute("PRAGMA quick_check").fetchone()
        except sqlite3.Error as exc:
            raise DatabaseError(
                "Veritabanı okunamıyor (bozulmuş olabilir). "
                "data/kurum_yedekleme.db dosyasını yedekleyip yeniden adlandırın; "
                "uygulama yeni bir veritabanı oluşturur."
            ) from exc
        status = str(row[0]) if row else "unknown"
        if status.lower() != "ok":
            raise DatabaseError(
                "Veritabanı bütünlük kontrolü başarısız (SQLite bozulmuş olabilir). "
                "data/kurum_yedekleme.db dosyasını yedekleyip yeniden adlandırın; "
                "uygulama yeni bir veritabanı oluşturur. "
                f"Ayrıntı: {status}"
            )

    def close(self) -> None:
        """Bağlantıyı kapatır."""
        if self._connection is not None:
            self._connection.close()
            self._connection = None
            logger.info("SQLite bağlantısı kapatıldı.")

    def __enter__(self) -> Database:
        self.connect()
        self.initialize()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()
