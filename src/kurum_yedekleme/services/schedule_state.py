"""Zamanlayıcı çalışma durumu (son otomatik yedekleme günü)."""

from __future__ import annotations

import logging
from datetime import date
from typing import Optional

from kurum_yedekleme.db.connection import Database
from kurum_yedekleme.db.errors import DatabaseError

logger = logging.getLogger(__name__)

KEY_LAST_AUTO_RUN_DATE = "schedule.last_auto_run_date"
KEY_MISSED_PROMPT_DATE = "schedule.missed_prompt_date"


class ScheduleStateStore:
    """SQLite settings tablosunda zamanlayıcı durumunu saklar."""

    def __init__(self, database: Database) -> None:
        self._db = database

    def get_last_auto_run_date(self) -> Optional[date]:
        value = self._get(KEY_LAST_AUTO_RUN_DATE)
        if not value:
            return None
        try:
            return date.fromisoformat(value)
        except ValueError:
            logger.warning("Geçersiz last_auto_run_date: %s", value)
            return None

    def set_last_auto_run_date(self, value: date) -> None:
        self._set(KEY_LAST_AUTO_RUN_DATE, value.isoformat())
        logger.info("Son otomatik yedekleme günü kaydedildi: %s", value)

    def get_missed_prompt_date(self) -> Optional[date]:
        value = self._get(KEY_MISSED_PROMPT_DATE)
        if not value:
            return None
        try:
            return date.fromisoformat(value)
        except ValueError:
            return None

    def set_missed_prompt_date(self, value: date) -> None:
        """Aynı gün kaçırılmış yedek sorusunu tekrar göstermemek için."""
        self._set(KEY_MISSED_PROMPT_DATE, value.isoformat())

    def get(self, key: str) -> Optional[str]:
        return self._get(key)

    def set(self, key: str, value: str) -> None:
        self._set(key, value)

    def _get(self, key: str) -> Optional[str]:
        conn = self._db.connect()
        row = conn.execute(
            "SELECT value FROM settings WHERE key = ?",
            (key,),
        ).fetchone()
        return str(row["value"]) if row else None

    def _set(self, key: str, value: str) -> None:
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        conn = self._db.connect()
        try:
            conn.execute(
                """
                INSERT INTO settings(key, value, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    updated_at = excluded.updated_at
                """,
                (key, value, now),
            )
            conn.commit()
        except Exception as exc:
            conn.rollback()
            raise DatabaseError(f"Ayar yazılamadı: {key}") from exc
