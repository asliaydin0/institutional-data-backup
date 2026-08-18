"""Tek alan için ZIP yedekleme — E:\\Yedekler\\Alan\\YYYY-MM-DD\\Alan.zip."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

from kurum_yedekleme.config.schema import AppSettings
from kurum_yedekleme.core.filenames import (
    area_folder_name,
    next_zip_path,
)
from kurum_yedekleme.core.progress import BackupProgressEvent, ProgressEmitter
from kurum_yedekleme.core.retry import RetryExhaustedError, RetryPolicy
from kurum_yedekleme.core.zipper import (
    BackupCancelledError,
    ZipBuildResult,
    Zipper,
    ZipperError,
    iter_source_files,
)
from kurum_yedekleme.db.models import BackupArea, BackupStatus, BackupType
from kurum_yedekleme.utils.app_logger import get_logger
from kurum_yedekleme.utils.formatting import format_bytes

logger = get_logger("BackupEngine")

CancelCheck = Callable[[], bool]


class BackupEngineError(Exception):
    """Yedekleme motoru hatası."""


@dataclass
class AreaBackupResult:
    """Tek alan yedekleme sonucu."""

    success: bool
    status: BackupStatus
    area: BackupArea
    backup_type: BackupType
    zip_path: Optional[Path]
    file_count: int
    zip_size: int
    started_at: datetime
    finished_at: datetime
    duration_seconds: float
    error_files: list[str] = field(default_factory=list)
    message: str = ""

    @property
    def cancelled(self) -> bool:
        return self.status == BackupStatus.CANCELLED


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def dated_area_directory(backup_root: Path, area_name: str, when: datetime) -> Path:
    local = when.astimezone() if when.tzinfo else when
    return (
        Path(backup_root)
        / area_folder_name(area_name)
        / local.strftime("%Y-%m-%d")
    )


class BackupEngine:
    """Bir alanı kaynak klasöründen E:\\Yedekler altına ZIP'ler."""

    def __init__(self, settings: AppSettings) -> None:
        self._settings = settings
        self._zipper = Zipper(
            compresslevel=settings.zip.compresslevel,
            exclude_patterns=settings.zip.exclude_patterns,
        )

    def update_settings(self, settings: AppSettings) -> None:
        self._settings = settings
        self._zipper = Zipper(
            compresslevel=settings.zip.compresslevel,
            exclude_patterns=settings.zip.exclude_patterns,
        )

    def backup_area(
        self,
        area: BackupArea,
        *,
        backup_type: BackupType,
        backup_root: Optional[Path] = None,
        progress_emitter: Optional[ProgressEmitter] = None,
        cancel_check: Optional[CancelCheck] = None,
    ) -> AreaBackupResult:
        started = _utc_now()
        started_mono = time.monotonic()
        source_path = Path(area.source_path)
        root = Path(backup_root or self._settings.backup_root)

        def emit(
            stage: str,
            message: str,
            *,
            current: int = 0,
            total: int = 0,
            percent: int = 0,
            zip_bytes: int = 0,
            current_path: str = "",
        ) -> None:
            if progress_emitter is None:
                return
            elapsed = max(0.0, time.monotonic() - started_mono)
            progress_emitter(
                BackupProgressEvent(
                    stage=stage,
                    message=message,
                    current_files=current,
                    total_files=total,
                    percent=max(0, min(100, percent)),
                    elapsed_seconds=elapsed,
                    zip_bytes=zip_bytes,
                    current_path=current_path,
                    area_name=area.name,
                )
            )

        logger.info(
            "Alan yedekleme başladı: %s tür=%s kaynak=%s",
            area.name,
            backup_type.value,
            source_path,
            operation="start",
        )
        emit("basladi", f"{area.name} yedekleniyor", percent=1)

        def fail(message: str, status: BackupStatus = BackupStatus.FAILED) -> AreaBackupResult:
            emit("hata" if status != BackupStatus.CANCELLED else "iptal", message, percent=100)
            logger.error("%s: %s", area.name, message, operation="finish")
            finished = _utc_now()
            return AreaBackupResult(
                success=False,
                status=status,
                area=area,
                backup_type=backup_type,
                zip_path=None,
                file_count=0,
                zip_size=0,
                started_at=started,
                finished_at=finished,
                duration_seconds=max(0.0, (finished - started).total_seconds()),
                message=message,
            )

        if cancel_check is not None and cancel_check():
            return fail("Yedekleme iptal edildi.", BackupStatus.CANCELLED)

        if not source_path.exists():
            return fail(f"Kaynak klasör bulunamadı: {source_path}")
        if not source_path.is_dir():
            return fail(f"Kaynak bir klasör değil: {source_path}")
        try:
            next(source_path.iterdir(), None)
        except PermissionError:
            return fail(f"Kaynak klasöre okuma izni yok: {source_path}")
        except OSError as exc:
            return fail(f"Kaynak klasöre erişilemiyor: {source_path} ({exc})")

        when_local = datetime.now().astimezone()
        dest_dir = dated_area_directory(root, area.name, when_local)
        try:
            dest_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            return fail(f"Hedef klasör oluşturulamadı: {dest_dir} ({exc})")

        final_zip = next_zip_path(dest_dir, area.name)
        _progress_state = {"t": 0.0, "percent": -1}

        def _progress(done: int, total: int, current: Path) -> None:
            percent = int((done / total) * 90) if total else 90
            percent = max(5, min(90, percent))
            now = time.monotonic()
            should_emit = (
                done <= 1
                or done == total
                or (
                    percent != _progress_state["percent"]
                    and (now - _progress_state["t"]) >= 0.2
                )
                or (now - _progress_state["t"]) >= 1.0
            )
            if not should_emit:
                return
            _progress_state["t"] = now
            _progress_state["percent"] = percent
            zip_bytes = 0
            tmp = dest_dir / f".{final_zip.stem}.tmp"
            for candidate in (tmp, final_zip):
                if candidate.exists():
                    try:
                        zip_bytes = candidate.stat().st_size
                        break
                    except OSError:
                        pass
            emit(
                "zip",
                f"{area.name}: ZIP oluşturuluyor ({done}/{total})",
                current=done,
                total=total,
                percent=percent,
                zip_bytes=zip_bytes,
                current_path=str(current),
            )

        retry = RetryPolicy(
            max_attempts=self._settings.retry.max_attempts,
            initial_delay_seconds=float(self._settings.retry.initial_delay_seconds),
            backoff_multiplier=float(self._settings.retry.backoff_multiplier),
        )

        try:
            emit("tarama", f"{area.name}: kaynak taranıyor...", percent=3)
            files = iter_source_files(
                source_path, self._settings.zip.exclude_patterns
            )
            logger.info(
                "Dosya sayısı: %s alan=%s",
                len(files),
                area.name,
                operation="scan",
            )
            emit(
                "zip",
                f"{area.name}: {len(files)} dosya ZIP'e ekleniyor...",
                current=0,
                total=len(files),
                percent=5,
            )
            def _create() -> ZipBuildResult:
                return self._zipper.create_archive(
                    source_path,
                    final_zip,
                    progress_callback=_progress,
                    files=files,
                    cancel_check=cancel_check,
                )

            def _retryable(exc: BaseException) -> bool:
                if isinstance(exc, BackupCancelledError):
                    return False
                return isinstance(exc, OSError)

            try:
                build = retry.run(
                    _create,
                    is_retryable=_retryable,
                    operation_name="ZIP",
                )
            except RetryExhaustedError as exc:
                return fail(str(exc))
            finished = _utc_now()
            duration = max(0.0, (finished - started).total_seconds())
            if build.error_files:
                sample = "; ".join(build.error_files[:3])
                if len(build.error_files) > 3:
                    sample += f" (+{len(build.error_files) - 3} dosya daha)"
                message = (
                    f"{len(build.error_files)} dosya ZIP'e eklenemedi; "
                    f"yedekleme eksik sayıldı. Örnek: {sample}"
                )
                emit("hata", message, percent=100)
                logger.error(
                    "%s: kısmi ZIP — %s dosya eklenemedi",
                    area.name,
                    len(build.error_files),
                    operation="finish",
                )
                return AreaBackupResult(
                    success=False,
                    status=BackupStatus.FAILED,
                    area=area,
                    backup_type=backup_type,
                    zip_path=build.zip_path,
                    file_count=build.file_count,
                    zip_size=build.zip_size,
                    started_at=started,
                    finished_at=finished,
                    duration_seconds=duration,
                    error_files=list(build.error_files),
                    message=message,
                )
            status = BackupStatus.SUCCESS
            message = "Yedekleme tamamlandı."
            emit(
                "tamamlandi",
                f"{area.name}: {format_bytes(build.zip_size)}",
                current=build.file_count,
                total=build.file_count,
                percent=100,
                zip_bytes=build.zip_size,
                current_path=str(build.zip_path),
            )
            logger.info(
                "Alan yedekleme başarılı: %s dosya=%s boyut=%s hedef=%s",
                area.name,
                build.file_count,
                format_bytes(build.zip_size),
                build.zip_path,
                operation="finish",
            )
            return AreaBackupResult(
                success=True,
                status=status,
                area=area,
                backup_type=backup_type,
                zip_path=build.zip_path,
                file_count=build.file_count,
                zip_size=build.zip_size,
                started_at=started,
                finished_at=finished,
                duration_seconds=duration,
                error_files=list(build.error_files),
                message=message,
            )
        except BackupCancelledError as exc:
            return fail(str(exc), BackupStatus.CANCELLED)
        except ZipperError as exc:
            return fail(str(exc))
        except PermissionError as exc:
            return fail(f"Erişim hatası: {exc}")
        except OSError as exc:
            err_no = getattr(exc, "errno", None)
            if err_no == 28:
                return fail(f"Diskte yeterli alan yok: {exc}")
            return fail(f"Dosya sistemi hatası: {exc}")
