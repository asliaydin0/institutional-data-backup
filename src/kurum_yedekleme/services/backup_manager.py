"""Merkezi yedekleme yöneticisi — GUI ve Windows Service aynı kodu kullanır."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Sequence

from kurum_yedekleme.config.schema import AppSettings
from kurum_yedekleme.core.backup_engine import AreaBackupResult, BackupEngine
from kurum_yedekleme.core.lock import BackupInProgressError, BackupLock
from kurum_yedekleme.core.progress import ProgressEmitter
from kurum_yedekleme.core.zipper import cleanup_orphan_tmps
from kurum_yedekleme.db.models import BackupArea, BackupStatus, BackupType
from kurum_yedekleme.services.disk_space import (
    BackupRootError,
    InsufficientDiskSpaceError,
    assert_disk_space,
    ensure_backup_root_writable,
    estimate_source_bytes,
    validate_production_backup_root,
)
from kurum_yedekleme.services.history_service import HistoryService
from kurum_yedekleme.utils.app_logger import get_logger

logger = get_logger("BackupManager")


@dataclass
class JobResult:
    backup_type: BackupType
    results: list[AreaBackupResult] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    error: str = ""

    @property
    def success_count(self) -> int:
        return sum(1 for item in self.results if item.success)

    @property
    def failed_count(self) -> int:
        return sum(
            1
            for item in self.results
            if item.status == BackupStatus.FAILED
        )

    @property
    def cancelled(self) -> bool:
        return any(item.cancelled for item in self.results)

    def format_report(self) -> str:
        lines = ["Yedekleme özeti", ""]
        if self.error:
            lines.append(self.error)
            lines.append("")
        for item in self.results:
            mark = item.status.label_tr
            size = f" {item.zip_size} bayt" if item.zip_path else ""
            lines.append(f"{item.area.name}: {mark}{size}")
            if item.message and not item.success:
                lines.append(f"  {item.message}")
        for skip in self.skipped:
            lines.append(f"Atlandı: {skip}")
        return "\n".join(lines)


class BackupManager:
    """Çoklu alan, kilit, geçmiş, E: kontrolleri."""

    def __init__(
        self,
        settings: AppSettings,
        *,
        history_service: HistoryService,
        lock: BackupLock,
        test_mode: bool = False,
    ) -> None:
        self._settings = settings
        self._history = history_service
        self._lock = lock
        self._engine = BackupEngine(settings)
        self._test_mode = bool(test_mode)
        self._cancel = threading.Event()
        self._busy = False
        self._busy_guard = threading.Lock()

    @property
    def is_busy(self) -> bool:
        return self._busy or self._lock.held

    @property
    def test_mode(self) -> bool:
        return self._test_mode

    def update_settings(self, settings: AppSettings) -> None:
        if self.is_busy:
            raise BackupInProgressError(
                "Yedekleme sürerken ayarlar güncellenemez."
            )
        self._settings = settings
        self._engine.update_settings(settings)

    def request_cancel(self) -> None:
        self._cancel.set()

    def run(
        self,
        areas: Sequence[BackupArea],
        *,
        backup_type: BackupType,
        progress_emitter: Optional[ProgressEmitter] = None,
        skip_successful_automatic_in_period: bool = False,
        schedule_frequency: str = "daily",
    ) -> JobResult:
        acquired = False
        try:
            self._lock.acquire(blocking=False)
            acquired = True
        except BackupInProgressError:
            raise

        with self._busy_guard:
            self._busy = True
        self._cancel.clear()
        job = JobResult(backup_type=backup_type)
        try:
            backup_root = self._prepare_root()
            cleanup_orphan_tmps(backup_root)
            selected = list(areas)
            if not selected:
                job.error = "Yedeklenecek aktif alan yok."
                return job

            logger.info(
                "Yedekleme işi başladı tür=%s alan=%s",
                backup_type.value,
                ", ".join(area.name for area in selected),
                operation="start",
            )

            needed = 0
            runnable: list[BackupArea] = []
            for area in selected:
                if (
                    skip_successful_automatic_in_period
                    and backup_type == BackupType.AUTOMATIC
                    and area.id is not None
                    and self._history.has_successful_automatic_in_period(
                        area.id, schedule_frequency
                    )
                ):
                    job.skipped.append(
                        f"{area.name}: bu dönemde başarılı otomatik yedek var"
                    )
                    logger.info(
                        "Otomatik yedek atlandı (dönemde SUCCESS): %s",
                        area.name,
                    )
                    continue
                runnable.append(area)
                needed += estimate_source_bytes(Path(area.source_path))

            if not runnable:
                return job

            assert_disk_space(backup_root, needed)

            for area in runnable:
                if self._cancel.is_set():
                    break
                result = self._run_one(
                    area,
                    backup_type=backup_type,
                    backup_root=backup_root,
                    progress_emitter=progress_emitter,
                )
                job.results.append(result)
                if result.cancelled:
                    break
            return job
        except (BackupRootError, InsufficientDiskSpaceError) as exc:
            job.error = str(exc)
            logger.error(str(exc))
            return job
        finally:
            if acquired:
                self._lock.release()
            with self._busy_guard:
                self._busy = False

    def _prepare_root(self) -> Path:
        root = Path(self._settings.backup_root)
        if not self._test_mode:
            validate_production_backup_root(root)
        return ensure_backup_root_writable(root)

    def _run_one(
        self,
        area: BackupArea,
        *,
        backup_type: BackupType,
        backup_root: Path,
        progress_emitter: Optional[ProgressEmitter],
    ) -> AreaBackupResult:
        record_id = self._history.start_run(
            area_id=area.id,
            area_name=area.name,
            backup_type=backup_type,
        )
        try:
            result = self._engine.backup_area(
                area,
                backup_type=backup_type,
                backup_root=backup_root,
                progress_emitter=progress_emitter,
                cancel_check=self._cancel.is_set,
            )
            if result.success and not result.zip_path:
                result.success = False
                result.status = BackupStatus.FAILED
                result.message = (
                    "ZIP dosyası oluşmadan yedekleme SUCCESS olamaz."
                )
            self._history.complete_from_result(record_id, result)
            logger.info(
                "Alan bitti name=%s status=%s type=%s size=%s path=%s",
                area.name,
                result.status.value,
                backup_type.value,
                result.zip_size,
                result.zip_path.name if result.zip_path else "-",
                operation="finish",
            )
            return result
        except Exception as exc:
            self._history.mark_failed(record_id, error_message=str(exc))
            raise
