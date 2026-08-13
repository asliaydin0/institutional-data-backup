"""Arka plan yedekleme işçisi (QThread) — UI'yi bloke etmez."""

from __future__ import annotations

import logging

from PySide6.QtCore import QThread, Signal

from kurum_yedekleme.core.progress import BackupProgressEvent
from kurum_yedekleme.services.backup_service import (
    BackupInProgressError,
    BackupService,
)

logger = logging.getLogger(__name__)


class BackupWorker(QThread):
    """Yedekleme motorunu ayrı thread'de çalıştırır."""

    progress = Signal(object)  # BackupProgressEvent
    finished_ok = Signal(str)
    finished_error = Signal(str)

    def __init__(
        self,
        backup_service: BackupService,
        *,
        trigger: str = "manual",
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._backup_service = backup_service
        self._trigger = trigger

    def run(self) -> None:
        def emit_progress(event: BackupProgressEvent) -> None:
            self.progress.emit(event)

        try:
            result = self._backup_service.run_backup(
                trigger=self._trigger,
                progress_emitter=emit_progress,
            )
            if result.success:
                self.finished_ok.emit(result.format_report())
            else:
                # Anlaşılır hata mesajı
                detail = result.transfer_message or result.message or result.status
                self.finished_error.emit(
                    f"Yedekleme tamamlanamadı.\n\n{detail}"
                )
        except BackupInProgressError as exc:
            self.finished_error.emit(str(exc))
        except Exception as exc:  # noqa: BLE001
            logger.exception("BackupWorker hatası")
            self.finished_error.emit(
                "Beklenmeyen bir hata oluştu.\n\n"
                f"{exc}\n\n"
                "Ayrıntılar için Loglar sayfasına bakın."
            )
