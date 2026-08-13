"""Uygulama durumu (ilk production yedek onayı vb.)."""

from __future__ import annotations

from kurum_yedekleme.db.connection import Database
from kurum_yedekleme.services.schedule_state import ScheduleStateStore

KEY_FIRST_PROD_BACKUP_DONE = "production.first_backup_done"


class AppStateStore:
    """SQLite settings üzerinden uygulama bayrakları."""

    def __init__(self, database: Database) -> None:
        self._store = ScheduleStateStore(database)

    def is_first_production_backup_pending(self) -> bool:
        return self._store.get(KEY_FIRST_PROD_BACKUP_DONE) != "1"

    def mark_first_production_backup_done(self) -> None:
        self._store.set(KEY_FIRST_PROD_BACKUP_DONE, "1")
