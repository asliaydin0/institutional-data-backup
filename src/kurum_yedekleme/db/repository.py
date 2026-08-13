"""Genel repository (uygulama olayları vb.)."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from kurum_yedekleme.db.connection import Database
from kurum_yedekleme.db.errors import DatabaseError

logger = logging.getLogger(__name__)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class Repository:
    """Uygulama olayları için hafif repository."""

    def __init__(self, database: Database) -> None:
        self._db = database

    def log_event(
        self,
        level: str,
        component: str,
        message: str,
        run_id: Optional[int] = None,
    ) -> None:
        """Yapısal uygulama olayını kaydeder."""
        conn = self._db.connect()
        try:
            conn.execute(
                """
                INSERT INTO app_events(created_at, level, component, message, run_id)
                VALUES (?, ?, ?, ?, ?)
                """,
                (_utc_now_iso(), level, component, message, run_id),
            )
            conn.commit()
        except Exception as exc:
            conn.rollback()
            logger.exception("Olay kaydı yazılamadı")
            raise DatabaseError("Olay kaydı yazılamadı.") from exc
