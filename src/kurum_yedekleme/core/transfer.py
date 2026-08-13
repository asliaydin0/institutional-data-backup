"""Ağ paylaşımına güvenli aktarım (.tmp → hash → nihai .zip)."""

from __future__ import annotations

import errno
import hashlib
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

from kurum_yedekleme.core.integrity import IntegrityChecker, IntegrityError
from kurum_yedekleme.core.retry import RetryExhaustedError, RetryPolicy
from kurum_yedekleme.utils.app_logger import get_logger
from kurum_yedekleme.utils.formatting import format_bytes
from kurum_yedekleme.utils.windows_paths import is_path_accessible, to_path

logger = get_logger("TransferService")

CHUNK_SIZE = 1024 * 1024

# Windows / ağ ile ilişkili yaygın winerror kodları
_NETWORK_WINERRORS = {
    5,  # Access denied (paylaşım)
    53,  # Network path not found
    64,  # Network name deleted
    65,  # Network access denied
    67,  # Network name not found
    121,  # Semaphore timeout
    1231,  # Network location cannot be reached
    1240,  # Account not authorized
    1326,  # Logon failure
    59,  # Unexpected network error
    88,  # Network error
}


class TransferError(Exception):
    """Aktarım hatası."""


class NetworkTransferError(TransferError):
    """Ağ bağlantısı / UNC erişim hatası."""


class IntegrityMismatchError(TransferError):
    """Yerel ve uzak hash uyuşmazlığı."""


@dataclass
class TransferResult:
    """Güvenli aktarım sonucu."""

    success: bool
    local_path: Path
    remote_final_path: Optional[Path]
    remote_tmp_path: Optional[Path]
    local_sha256: Optional[str]
    remote_sha256: Optional[str]
    local_size: int
    remote_size: int
    attempts: int
    message: str

    def format_report(self) -> str:
        lines = [
            "Aktarım özeti",
            f"Yerel ZIP: {self.local_path}",
            f"Deneme: {self.attempts}",
        ]
        if self.remote_final_path is not None:
            lines.append(f"Uzak dosya: {self.remote_final_path}")
        if self.local_sha256:
            lines.append(f"Yerel SHA-256: {self.local_sha256}")
        if self.remote_sha256:
            lines.append(f"Uzak SHA-256: {self.remote_sha256}")
        lines.append(f"Durum: {'BAŞARILI' if self.success else 'BAŞARISIZ'}")
        if self.message:
            lines.append(self.message)
        return "\n".join(lines)


def is_retryable_transfer_error(exc: BaseException) -> bool:
    """Ağ / IO hatalarında yeniden denenebilir mi?"""
    if isinstance(exc, IntegrityMismatchError):
        # Hash uyuşmazlığı da yeniden denemeye değer (bozuk aktarım)
        return True
    if isinstance(exc, NetworkTransferError):
        return True
    if isinstance(exc, IntegrityError):
        return True
    if isinstance(exc, OSError):
        winerror = getattr(exc, "winerror", None)
        if winerror in _NETWORK_WINERRORS:
            return True
        # Genel IO: bağlantı kopması vb.
        return True
    return False


def date_subdir_name(when: Optional[datetime] = None) -> str:
    """YYYY-MM-DD tarih klasör adı."""
    moment = when or datetime.now().astimezone()
    return moment.strftime("%Y-%m-%d")


class TransferService:
    """
    Yerel ZIP → hedef (.tmp) → boyut + SHA-256 → nihai .zip.

    Kaynak ZIP bu modül tarafından asla silinmez.
    """

    def __init__(
        self,
        *,
        max_attempts: int = 3,
        initial_delay_seconds: float = 5.0,
        backoff_multiplier: float = 2.0,
        chunk_size: int = CHUNK_SIZE,
        integrity: Optional[IntegrityChecker] = None,
        sleep_fn: Optional[Callable[[float], None]] = None,
    ) -> None:
        self.chunk_size = chunk_size
        self.integrity = integrity or IntegrityChecker()
        retry_kwargs = {
            "max_attempts": max_attempts,
            "initial_delay_seconds": initial_delay_seconds,
            "backoff_multiplier": backoff_multiplier,
        }
        if sleep_fn is not None:
            retry_kwargs["sleep_fn"] = sleep_fn
        self._retry = RetryPolicy(**retry_kwargs)
        self.max_attempts = max_attempts

    def ensure_destination_accessible(self, destination_root: Path | str) -> Path:
        """Sunucu / hedef yolunun erişilebilir olduğunu doğrular."""
        root = to_path(destination_root)
        logger.info("Hedef erişim kontrolü: %s", root)
        try:
            if not is_path_accessible(root):
                raise NetworkTransferError(
                    f"Hedef yol erişilebilir değil veya bulunamadı: {root}"
                )
            # Yazılabilirlik için hafif kontrol — listeleme
            _ = list(root.iterdir()) if root.is_dir() else None
            if not root.is_dir():
                raise NetworkTransferError(f"Hedef bir klasör değil: {root}")
        except NetworkTransferError:
            raise
        except OSError as exc:
            raise NetworkTransferError(
                f"Ağ/hedef erişim hatası: {root} ({exc})"
            ) from exc
        logger.info("Hedef erişilebilir: %s", root)
        return root

    def prepare_dated_directory(
        self,
        destination_root: Path | str,
        *,
        create_subdirs_by_date: bool = True,
        when: Optional[datetime] = None,
    ) -> Path:
        """Gerekirse YYYY-MM-DD alt klasörünü oluşturur."""
        root = self.ensure_destination_accessible(destination_root)
        if not create_subdirs_by_date:
            return root
        dated = root / date_subdir_name(when)
        try:
            dated.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise NetworkTransferError(
                f"Tarih klasörü oluşturulamadı: {dated} ({exc})"
            ) from exc
        logger.info("Hedef tarih klasörü hazır: %s", dated)
        return dated

    def transfer_zip(
        self,
        local_zip: Path | str,
        destination_root: Path | str,
        *,
        remote_filename: Optional[str] = None,
        create_subdirs_by_date: bool = True,
        when: Optional[datetime] = None,
    ) -> TransferResult:
        """
        ZIP'i güvenli şekilde hedefe aktarır.

        Akış: erişim → tarih klasörü → .tmp kopya → boyut → SHA-256 → rename.
        Yerel ZIP silinmez.
        """
        local_path = Path(local_zip)
        if not local_path.is_file():
            raise TransferError(f"Yerel ZIP bulunamadı: {local_path}")

        local_size = local_path.stat().st_size
        filename = remote_filename or local_path.name
        if not filename.lower().endswith(".zip"):
            filename = f"{filename}.zip"

        attempts_used = 0

        def _attempt() -> TransferResult:
            nonlocal attempts_used
            attempts_used += 1
            return self._transfer_once(
                local_path=local_path,
                local_size=local_size,
                destination_root=destination_root,
                filename=filename,
                create_subdirs_by_date=create_subdirs_by_date,
                when=when,
                attempt_no=attempts_used,
            )

        try:
            return self._retry.run(
                _attempt,
                is_retryable=is_retryable_transfer_error,
                operation_name="Aktarım",
            )
        except RetryExhaustedError as exc:
            logger.error("Aktarım tüm denemelerde başarısız: %s", exc)
            return TransferResult(
                success=False,
                local_path=local_path,
                remote_final_path=None,
                remote_tmp_path=None,
                local_sha256=None,
                remote_sha256=None,
                local_size=local_size,
                remote_size=0,
                attempts=attempts_used,
                message=str(exc),
            )
        except TransferError as exc:
            logger.error("Aktarım hatası: %s", exc)
            return TransferResult(
                success=False,
                local_path=local_path,
                remote_final_path=None,
                remote_tmp_path=None,
                local_sha256=None,
                remote_sha256=None,
                local_size=local_size,
                remote_size=0,
                attempts=max(attempts_used, 1),
                message=str(exc),
            )

    def _transfer_once(
        self,
        *,
        local_path: Path,
        local_size: int,
        destination_root: Path | str,
        filename: str,
        create_subdirs_by_date: bool,
        when: Optional[datetime],
        attempt_no: int,
    ) -> TransferResult:
        target_dir = self.prepare_dated_directory(
            destination_root,
            create_subdirs_by_date=create_subdirs_by_date,
            when=when,
        )
        remote_final = target_dir / filename
        remote_tmp = target_dir / f"{filename}.tmp"

        logger.info(
            "Sunucuya aktarım başladı (deneme %s): %s → %s",
            attempt_no,
            local_path,
            remote_tmp,
            operation="transfer",
        )

        # Önceki yarım kalmış tmp temizliği
        self._safe_unlink(remote_tmp, reason="eski tmp temizliği")

        try:
            local_hash = self._copy_to_tmp(local_path, remote_tmp)

            remote_size = remote_tmp.stat().st_size
            logger.info(
                "Boyut kontrolü: yerel=%s uzak_tmp=%s",
                format_bytes(local_size),
                format_bytes(remote_size),
            )
            if remote_size != local_size:
                raise TransferError(
                    f"Boyut uyuşmazlığı: yerel={local_size} uzak={remote_size}"
                )

            # Yerel hash kopyalama sırasında hesaplandı — ikinci yerel okuma yok
            remote_hash = self.integrity.sha256_file(remote_tmp)
            logger.info("Hash karşılaştırılıyor...", operation="verify")
            if local_hash.lower() != remote_hash.lower():
                raise IntegrityMismatchError(
                    f"SHA-256 uyuşmazlığı: yerel={local_hash} uzak={remote_hash}"
                )

            # Nihai ada dönüştür (doğrudan nihai adla kopyalanmadı)
            if remote_final.exists():
                logger.warning(
                    "Hedefte aynı adlı dosya var, üzerine yazılacak: %s",
                    remote_final,
                    operation="transfer",
                )
                self._safe_unlink(remote_final, reason="eski nihai dosya")

            os.replace(remote_tmp, remote_final)
            logger.info(
                "SHA-256 doğrulaması başarılı",
                operation="verify",
            )
            logger.info("Nihai dosya hazır: %s", remote_final, operation="transfer")

            # Yerel ZIP bilinçli olarak silinmez
            if not local_path.is_file():
                logger.error(
                    "Beklenmeyen durum: yerel ZIP aktarım sonrası yok: %s",
                    local_path,
                )

            return TransferResult(
                success=True,
                local_path=local_path,
                remote_final_path=remote_final,
                remote_tmp_path=remote_tmp,
                local_sha256=local_hash,
                remote_sha256=remote_hash,
                local_size=local_size,
                remote_size=remote_size,
                attempts=attempt_no,
                message="Aktarım ve bütünlük doğrulaması başarılı.",
            )
        except Exception:
            self._safe_unlink(remote_tmp, reason="başarısız aktarım temizliği")
            raise

    def _copy_to_tmp(self, local_path: Path, remote_tmp: Path) -> str:
        """
        ZIP'i yalnızca .tmp adına chunk'lı kopyalar; yerel SHA-256'yı aynı geçişte üretir.

        Böylece büyük dosyalarda ikinci kez yerel disk okunmaz.
        """
        hasher = hashlib.sha256()
        try:
            with local_path.open("rb") as src, remote_tmp.open("wb") as dest:
                while True:
                    chunk = src.read(self.chunk_size)
                    if not chunk:
                        break
                    hasher.update(chunk)
                    dest.write(chunk)
                dest.flush()
                os.fsync(dest.fileno())
        except OSError as exc:
            winerror = getattr(exc, "winerror", None)
            err_no = getattr(exc, "errno", None)
            if err_no == errno.ENOSPC or winerror in {112, 39}:  # disk full
                raise NetworkTransferError(
                    "Sunucu diskinde yeterli alan yok; aktarım iptal edildi."
                ) from exc
            if winerror == 5 or err_no in {errno.EACCES, errno.EPERM}:
                raise NetworkTransferError(
                    "Sunucuya dosya yazma izni yok; aktarım iptal edildi."
                ) from exc
            if winerror in _NETWORK_WINERRORS:
                raise NetworkTransferError(
                    f"Ağ bağlantısı kopmuş veya hedefe yazılamıyor: {exc}"
                ) from exc
            raise NetworkTransferError(
                f"Aktarım IO hatası (.tmp): {exc}"
            ) from exc
        return hasher.hexdigest()

    @staticmethod
    def _safe_unlink(path: Path, *, reason: str) -> None:
        try:
            if path.exists():
                path.unlink()
                logger.info("Silindi (%s): %s", reason, path)
        except OSError as exc:
            logger.warning("Silinemedi (%s): %s (%s)", reason, path, exc)
