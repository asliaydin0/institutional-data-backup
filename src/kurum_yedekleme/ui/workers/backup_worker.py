"""Arka plan yedekleme işçisi (QThread)."""

from __future__ import annotations

import logging
from typing import Sequence

from PySide6.QtCore import QThread, Signal

from kurum_yedekleme.core.lock import BackupInProgressError
from kurum_yedekleme.core.progress import BackupProgressEvent
from kurum_yedekleme.db.models import BackupArea, BackupType
from kurum_yedekleme.services.backup_manager import BackupManager, JobResult

logger = logging.getLogger(__name__)


class BackupWorker(QThread):
    progress = Signal(object)
    finished_ok = Signal(str)
    finished_error = Signal(str)

    def __init__(
        self,
        backup_manager: BackupManager,
        areas: Sequence[BackupArea],
        *,
        backup_type: BackupType = BackupType.MANUAL,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._manager = backup_manager
        self._areas = list(areas)
        self._backup_type = backup_type

    def cancel(self) -> None:
        self._manager.request_cancel()

    def run(self) -> None:
        def emit_progress(event: BackupProgressEvent) -> None:
            self.progress.emit(event)

        try:
            job: JobResult = self._manager.run(
                self._areas,
                backup_type=self._backup_type,
                progress_emitter=emit_progress,
                skip_successful_automatic_in_period=(
                    self._backup_type == BackupType.AUTOMATIC
                ),
            )
            report = job.format_report()
            if job.error and not job.results:
                self.finished_error.emit(job.error)
                return
            if job.failed_count and job.success_count == 0 and not job.cancelled:
                self.finished_error.emit(report)
                return
            if job.cancelled:
                self.finished_error.emit(report)
                return
            if job.failed_count:
                self.finished_error.emit(report)
                return
            self.finished_ok.emit(report)
        except BackupInProgressError as exc:
            self.finished_error.emit(str(exc))
        except Exception as exc:  # noqa: BLE001
            logger.exception("BackupWorker hatası")
            self.finished_error.emit(
                "Beklenmeyen bir hata oluştu.\n\n"
                f"{exc}\n\n"
                "Ayrıntılar için Loglar sayfasına bakın."
            )
