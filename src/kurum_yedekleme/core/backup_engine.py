"""Ana yedekleme orkestrasyonu — ZIP + güvenli aktarım."""

from __future__ import annotations

import socket
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

from kurum_yedekleme.config.schema import AppSettings, SourceConfig
from kurum_yedekleme.core.progress import BackupProgressEvent, ProgressEmitter
from kurum_yedekleme.core.transfer import TransferResult, TransferService
from kurum_yedekleme.core.zipper import Zipper, ZipperError
from kurum_yedekleme.utils.app_logger import get_logger
from kurum_yedekleme.utils.formatting import format_bytes

logger = get_logger("BackupEngine")

ProgressCallback = Callable[[int, int, Path], None]


class BackupEngineError(Exception):
    """Yedekleme motoru hatası."""


@dataclass
class BackupResult:
    """Tek kaynaklı ZIP yedekleme (+ isteğe bağlı aktarım) sonucu."""

    success: bool
    status: str
    source_path: Path
    zip_path: Optional[Path]
    file_count: int
    original_size: int
    zip_size: int
    compression_ratio_percent: float
    started_at: datetime
    finished_at: datetime
    trigger: str
    error_files: list[str] = field(default_factory=list)
    message: str = ""
    remote_path: Optional[Path] = None
    local_sha256: Optional[str] = None
    remote_sha256: Optional[str] = None
    transfer_attempts: int = 0
    transfer_message: str = ""

    def format_report(self) -> str:
        """Kullanıcıya gösterilecek Türkçe özet."""
        lines = [
            "Yedekleme başladı",
            f"Kaynak: {self.source_path}",
            "",
            f"Dosya sayısı: {self.file_count}",
            f"Orijinal boyut: {format_bytes(self.original_size)}",
            "",
        ]
        if self.zip_path is not None:
            lines.extend(
                [
                    "ZIP oluşturuluyor...",
                    "İlerleme: %100",
                    "",
                    "ZIP tamamlandı.",
                    f"ZIP boyutu: {format_bytes(self.zip_size)}",
                    f"Sıkıştırma oranı: %{self.compression_ratio_percent:.0f}",
                    f"Yerel ZIP: {self.zip_path}",
                ]
            )
        if self.remote_path is not None or self.transfer_message:
            lines.append("")
            lines.append("Sunucu aktarımı...")
            if self.local_sha256:
                lines.append(f"Yerel SHA-256: {self.local_sha256}")
            if self.remote_sha256:
                lines.append(f"Uzak SHA-256: {self.remote_sha256}")
            if self.transfer_attempts:
                lines.append(f"Aktarım denemesi: {self.transfer_attempts}")
            if self.remote_path is not None:
                lines.append(f"Uzak dosya: {self.remote_path}")
            if self.transfer_message:
                lines.append(self.transfer_message)
        lines.extend(
            [
                "",
                f"Durum: {self.status}",
                f"Başlangıç: {self.started_at.isoformat()}",
                f"Bitiş: {self.finished_at.isoformat()}",
            ]
        )
        if self.message and not self.success:
            lines.append(self.message)
        if self.error_files:
            lines.append("")
            lines.append(f"Hatalı dosya sayısı: {len(self.error_files)}")
            for err in self.error_files[:20]:
                lines.append(f"  - {err}")
            if len(self.error_files) > 20:
                lines.append(f"  ... +{len(self.error_files) - 20} daha")
        # Yerel ZIP koruma notu
        if self.zip_path is not None and self.zip_path.exists():
            lines.append("")
            lines.append(f"Yerel ZIP korundu: {self.zip_path}")
        return "\n".join(lines)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def build_zip_filename(pattern: str, when: Optional[datetime] = None) -> str:
    """filename_pattern şablonundan ZIP adı üretir."""
    moment = when or _utc_now()
    local = moment.astimezone() if moment.tzinfo else moment
    hostname = socket.gethostname() or "host"
    return (
        pattern.replace("{date}", local.strftime("%Y-%m-%d"))
        .replace("{time}", local.strftime("%H%M%S"))
        .replace("{hostname}", hostname)
    )


class BackupEngine:
    """Güvenli ZIP üretimi ve ağ paylaşımına doğrulanmış aktarım."""

    def __init__(self, settings: AppSettings) -> None:
        self._settings = settings
        self._zipper = Zipper(
            compresslevel=settings.zip.compresslevel,
            exclude_patterns=settings.zip.exclude_patterns,
        )
        self._transfer = TransferService(
            max_attempts=settings.retry.max_attempts,
            initial_delay_seconds=float(settings.retry.initial_delay_seconds),
            backoff_multiplier=float(settings.retry.backoff_multiplier),
        )

    def run_backup(
        self,
        *,
        trigger: str = "manual",
        source: Optional[SourceConfig | Path | str] = None,
        temp_dir: Optional[Path | str] = None,
        destination: Optional[Path | str] = None,
        transfer: bool = True,
        progress_callback: Optional[ProgressCallback] = None,
        progress_emitter: Optional[ProgressEmitter] = None,
    ) -> BackupResult:
        """
        Kaynak → yerel ZIP → (isteğe bağlı) güvenli sunucu aktarımı.

        Yerel ZIP, sunucuda doğrulansa bile bu aşamada silinmez.
        """
        started = _utc_now()
        started_mono = datetime.now().timestamp()
        source_path = self._resolve_source(source)
        out_dir = self._resolve_temp_dir(temp_dir)

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
            elapsed = max(0.0, datetime.now().timestamp() - started_mono)
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
                )
            )

        logger.info("Yedekleme başlatıldı", operation="start")
        logger.info("Kaynak: %s", source_path, operation="start")
        logger.info("Geçici ZIP klasörü: %s", out_dir, operation="start")
        emit("basladi", "Yedekleme başlatıldı", percent=1)

        if not source_path.exists():
            emit("hata", f"Kaynak klasör bulunamadı: {source_path}", percent=0)
            return self._fail(
                started=started,
                source_path=source_path,
                trigger=trigger,
                message=f"Kaynak klasör bulunamadı: {source_path}",
            )

        if not source_path.is_dir():
            emit("hata", f"Kaynak bir klasör değil: {source_path}", percent=0)
            return self._fail(
                started=started,
                source_path=source_path,
                trigger=trigger,
                message=f"Kaynak bir klasör değil: {source_path}",
            )

        out_dir.mkdir(parents=True, exist_ok=True)
        when_local = datetime.now().astimezone()
        zip_name = build_zip_filename(
            self._settings.destination.filename_pattern, when=when_local
        )
        final_zip = out_dir / zip_name

        _progress_state = {"t": 0.0, "percent": -1}

        def _progress(done: int, total: int, current: Path) -> None:
            percent = int((done / total) * 80) if total else 80  # ZIP ~%80
            percent = max(5, min(80, percent))
            if done == 1 or done == total or done % 25 == 0:
                logger.info("İlerleme: %%%s (%s/%s)", percent, done, total)
            if progress_callback is not None:
                progress_callback(done, total, current)

            # GUI sinyal selini önle: zaman + yüzde eşiği
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
            partial = Path(str(final_zip) + ".partial")
            for candidate in (partial, final_zip):
                if candidate.exists():
                    try:
                        zip_bytes = candidate.stat().st_size
                        break
                    except OSError:
                        pass
            emit(
                "zip",
                f"ZIP oluşturuluyor ({done}/{total})",
                current=done,
                total=total,
                percent=percent,
                zip_bytes=zip_bytes,
                current_path=str(current),
            )

        try:
            from kurum_yedekleme.core.zipper import iter_source_files

            emit("tarama", "Kaynak dosyalar taranıyor...", percent=3)
            logger.info("Kaynak taranıyor", operation="scan")
            files = iter_source_files(
                source_path, self._settings.zip.exclude_patterns
            )
            logger.info("Dosya sayısı: %s", len(files), operation="scan")
            logger.info("ZIP oluşturuluyor...", operation="zip")
            emit(
                "zip",
                f"{len(files)} dosya ZIP'e ekleniyor...",
                current=0,
                total=len(files),
                percent=5,
            )

            build = self._zipper.create_archive(
                source_path,
                final_zip,
                progress_callback=_progress,
                files=files,
            )
            logger.info("ZIP oluşturuldu", operation="zip")
            logger.info(
                "Orijinal boyut: %s",
                format_bytes(build.original_size),
                operation="scan",
            )
            logger.info("ZIP boyutu: %s", format_bytes(build.zip_size), operation="zip")
            logger.info(
                "Sıkıştırma oranı: %%%s",
                f"{build.compression_ratio_percent:.0f}",
                operation="zip",
            )
            emit(
                "zip",
                "ZIP tamamlandı",
                current=build.file_count,
                total=build.file_count,
                percent=82,
                zip_bytes=build.zip_size,
            )

            transfer_result: Optional[TransferResult] = None
            if transfer:
                dest_root = (
                    Path(destination)
                    if destination is not None
                    else Path(self._settings.destination.unc_path)
                )
                logger.info("Sunucuya aktarım başladı", operation="transfer")
                emit(
                    "aktarim",
                    "Sunucuya aktarılıyor...",
                    current=build.file_count,
                    total=build.file_count,
                    percent=88,
                    zip_bytes=build.zip_size,
                )
                transfer_result = self._transfer.transfer_zip(
                    build.zip_path,
                    dest_root,
                    remote_filename=build.zip_path.name,
                    create_subdirs_by_date=(
                        self._settings.destination.create_subdirs_by_date
                    ),
                    when=when_local,
                )
                if transfer_result.success:
                    logger.info(
                        "SHA-256 doğrulaması başarılı",
                        operation="verify",
                    )
                emit(
                    "dogrulama",
                    "SHA-256 doğrulaması tamamlandı"
                    if transfer_result.success
                    else "Aktarım doğrulaması başarısız",
                    current=build.file_count,
                    total=build.file_count,
                    percent=95 if transfer_result.success else 90,
                    zip_bytes=build.zip_size,
                )
                if not build.zip_path.exists():
                    logger.error(
                        "Kritik: yerel ZIP aktarım sonrası silinmiş: %s",
                        build.zip_path,
                        operation="transfer",
                    )

            finished = _utc_now()
            if transfer and transfer_result is not None and not transfer_result.success:
                emit(
                    "hata",
                    transfer_result.message or "Sunucu aktarımı başarısız",
                    current=build.file_count,
                    total=build.file_count,
                    percent=100,
                    zip_bytes=build.zip_size,
                )
                return BackupResult(
                    success=False,
                    status="BAŞARISIZ",
                    source_path=source_path,
                    zip_path=build.zip_path,
                    file_count=build.file_count,
                    original_size=build.original_size,
                    zip_size=build.zip_size,
                    compression_ratio_percent=build.compression_ratio_percent,
                    started_at=started,
                    finished_at=finished,
                    trigger=trigger,
                    error_files=list(build.error_files),
                    message="ZIP oluştu ancak sunucu aktarımı başarısız.",
                    remote_path=transfer_result.remote_final_path,
                    local_sha256=transfer_result.local_sha256,
                    remote_sha256=transfer_result.remote_sha256,
                    transfer_attempts=transfer_result.attempts,
                    transfer_message=transfer_result.message,
                )

            status = "BAŞARILI"
            if build.error_files:
                status = "BAŞARILI (uyarılar var)"

            result = BackupResult(
                success=True,
                status=status,
                source_path=source_path,
                zip_path=build.zip_path,
                file_count=build.file_count,
                original_size=build.original_size,
                zip_size=build.zip_size,
                compression_ratio_percent=build.compression_ratio_percent,
                started_at=started,
                finished_at=finished,
                trigger=trigger,
                error_files=list(build.error_files),
                message="Yedekleme tamamlandı.",
                remote_path=(
                    transfer_result.remote_final_path if transfer_result else None
                ),
                local_sha256=(
                    transfer_result.local_sha256 if transfer_result else None
                ),
                remote_sha256=(
                    transfer_result.remote_sha256 if transfer_result else None
                ),
                transfer_attempts=(
                    transfer_result.attempts if transfer_result else 0
                ),
                transfer_message=(
                    transfer_result.message if transfer_result else ""
                ),
            )
            emit(
                "tamamlandi",
                "Yedekleme başarıyla tamamlandı",
                current=build.file_count,
                total=build.file_count,
                percent=100,
                zip_bytes=build.zip_size,
            )
            logger.info("Durum: %s", result.status, operation="finish")
            if result.success:
                logger.info("Yedekleme başarılı", operation="finish")
            self._cleanup_temp_artifacts(out_dir, final_zip)
            return result

        except ZipperError as exc:
            logger.exception("ZIP hatası")
            emit("hata", str(exc), percent=100)
            return self._fail(
                started=started,
                source_path=source_path,
                trigger=trigger,
                message=str(exc),
            )
        except PermissionError as exc:
            logger.exception("Erişim hatası")
            message = f"Kaynak klasöre veya dosyaya erişim yok: {exc}"
            emit("hata", message, percent=100)
            return self._fail(
                started=started,
                source_path=source_path,
                trigger=trigger,
                message=message,
            )
        except OSError as exc:
            logger.exception("IO hatası")
            err_no = getattr(exc, "errno", None)
            if err_no == 28:  # ENOSPC
                message = f"Diskte yeterli alan yok: {exc}"
            else:
                message = f"Dosya sistemi hatası: {exc}"
            emit("hata", message, percent=100)
            return self._fail(
                started=started,
                source_path=source_path,
                trigger=trigger,
                message=message,
            )

    @staticmethod
    def _safe_size(path: Path) -> int:
        try:
            return path.stat().st_size
        except OSError:
            return 0

    @staticmethod
    def _cleanup_temp_artifacts(temp_dir: Path, final_zip: Path) -> None:
        """İşlem sonunda gereksiz .partial kalıntılarını temizler (nihai ZIP korunur)."""
        partial = Path(str(final_zip) + ".partial")
        if partial.exists():
            try:
                partial.unlink()
                logger.info("Geçici partial silindi: %s", partial, operation="cleanup")
            except OSError as exc:
                logger.warning("Partial silinemedi: %s (%s)", partial, exc)
        # Eski orphan .partial dosyaları (önceki kesintiler)
        try:
            for orphan in temp_dir.glob("*.partial"):
                try:
                    orphan.unlink()
                    logger.info("Orphan partial silindi: %s", orphan, operation="cleanup")
                except OSError:
                    pass
        except OSError:
            pass

    def _fail(
        self,
        *,
        started: datetime,
        source_path: Path,
        trigger: str,
        message: str,
        zip_path: Optional[Path] = None,
    ) -> BackupResult:
        logger.error(message)
        return BackupResult(
            success=False,
            status="BAŞARISIZ",
            source_path=source_path,
            zip_path=zip_path,
            file_count=0,
            original_size=0,
            zip_size=0,
            compression_ratio_percent=0.0,
            started_at=started,
            finished_at=_utc_now(),
            trigger=trigger,
            message=message,
        )

    def _resolve_source(
        self, source: Optional[SourceConfig | Path | str]
    ) -> Path:
        if source is None:
            enabled = [s for s in self._settings.sources if s.enabled]
            if not enabled:
                raise BackupEngineError(
                    "Etkin kaynak klasörü yapılandırmada tanımlı değil."
                )
            return Path(enabled[0].path)
        if isinstance(source, SourceConfig):
            return Path(source.path)
        return Path(source)

    def _resolve_temp_dir(self, temp_dir: Optional[Path | str]) -> Path:
        if temp_dir is not None:
            return Path(temp_dir)
        return Path(self._settings.app.temp_dir)
