"""Güvenli ZIP oluşturma — kaynaklar yalnızca okunur."""

from __future__ import annotations

import fnmatch
import os
import shutil
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional, Sequence

from kurum_yedekleme.utils.app_logger import get_logger

logger = get_logger("ZipEngine")

ProgressCallback = Callable[[int, int, Path], None]
"""(işlenen_dosya_sayısı, toplam_dosya, mevcut_dosya) → None"""


class ZipperError(Exception):
    """ZIP oluşturma hatası."""


@dataclass
class ZipBuildResult:
    """ZIP oluşturma sonucu."""

    zip_path: Path
    file_count: int
    original_size: int
    zip_size: int
    compression_ratio_percent: float
    skipped_files: list[str] = field(default_factory=list)
    error_files: list[str] = field(default_factory=list)


def _matches_exclude(name: str, patterns: Sequence[str]) -> bool:
    return any(fnmatch.fnmatch(name, pattern) for pattern in patterns)


def iter_source_files(
    source_root: Path,
    exclude_patterns: Sequence[str] | None = None,
) -> list[Path]:
    """
    Kaynak klasördeki dosyaları özyinelemeli listeler.

    Yalnızca dosyalar döner; klasör girdileri eklenmez.
    """
    patterns = list(exclude_patterns or [])
    root = source_root.resolve()
    files: list[Path] = []

    for dirpath, _dirnames, filenames in os.walk(root, followlinks=False):
        current = Path(dirpath)
        for filename in filenames:
            if _matches_exclude(filename, patterns):
                logger.debug("Hariç tutuldu: %s", current / filename)
                continue
            path = current / filename
            if path.is_symlink():
                logger.warning("Sembolik bağlantı atlandı: %s", path)
                continue
            if path.is_file():
                files.append(path)
    files.sort(key=lambda p: str(p).lower())
    return files


def safe_arcname(source_root: Path, file_path: Path) -> str:
    """
    ZIP içi göreli yolu üretir (POSIX ayırıcı).

    Path traversal (.. ) engellenir.
    """
    root = source_root.resolve()
    resolved = file_path.resolve()
    try:
        relative = resolved.relative_to(root)
    except ValueError as exc:
        raise ZipperError(
            f"Dosya kaynak kökünün dışında: {file_path}"
        ) from exc
    if any(part == ".." for part in relative.parts):
        raise ZipperError(f"Geçersiz göreli yol: {relative}")
    return relative.as_posix()


def _set_utf8_flag(info: zipfile.ZipInfo) -> None:
    """Türkçe/Unicode dosya adları için UTF-8 bayrağını açar."""
    info.flag_bits |= 0x800


def _open_source_readonly(path: Path):
    """Kaynağı salt okunur açar (yazma/silme yok)."""
    return open(path, "rb")  # noqa: SIM115 — çağıran kapatır


def verify_zip(zip_path: Path) -> None:
    """ZIP bütünlüğünü testzip ile doğrular."""
    try:
        with zipfile.ZipFile(zip_path, mode="r") as archive:
            bad = archive.testzip()
            if bad is not None:
                raise ZipperError(f"Bozuk ZIP üyesi: {bad}")
            # En azından merkezi dizin okunabilmeli
            _ = archive.namelist()
    except zipfile.BadZipFile as exc:
        raise ZipperError(f"ZIP bozuk veya okunamıyor: {zip_path}") from exc


class Zipper:
    """Kaynak klasörden salt-okunur, atomik ZIP üretici."""

    def __init__(
        self,
        *,
        compresslevel: int = 6,
        exclude_patterns: Optional[Sequence[str]] = None,
        chunk_size: int = 1024 * 1024,
    ) -> None:
        self.compresslevel = compresslevel
        self.exclude_patterns = list(exclude_patterns or [])
        self.chunk_size = chunk_size

    def create_archive(
        self,
        source_root: Path,
        final_zip_path: Path,
        *,
        progress_callback: Optional[ProgressCallback] = None,
        files: Optional[Sequence[Path]] = None,
    ) -> ZipBuildResult:
        """
        Kaynak klasörü geçici ZIP'e yazar, doğrular, nihai ada taşır.

        Kaynak dosyalara yazılmaz / silinmez.
        files verilirse ikinci kez dizin taraması yapılmaz (büyük ağaçlar).
        """
        source_root = Path(source_root)
        final_zip_path = Path(final_zip_path)

        if not source_root.exists():
            raise ZipperError(f"Kaynak klasör bulunamadı: {source_root}")
        if not source_root.is_dir():
            raise ZipperError(f"Kaynak bir klasör değil: {source_root}")

        final_zip_path.parent.mkdir(parents=True, exist_ok=True)
        partial_path = final_zip_path.with_suffix(final_zip_path.suffix + ".partial")
        if partial_path.exists():
            partial_path.unlink()
        if final_zip_path.exists():
            # Aynı ada üzerine yazmadan önce eski nihai dosyayı kaldırma —
            # yalnızca partial üzerinden atomik replace ile değişir.
            # Çakışmayı önlemek için partial hazırlanana kadar final'e dokunulmaz;
            # replace anında üzerine yazılır.
            pass

        file_list: list[Path] = (
            list(files)
            if files is not None
            else iter_source_files(source_root, self.exclude_patterns)
        )
        total = len(file_list)
        original_size = 0
        added = 0
        error_files: list[str] = []
        skipped_files: list[str] = []

        # Boyut toplamı ZIP döngüsünde tek seferde alınır (çift stat yok)

        logger.info("ZIP oluşturuluyor (geçici): %s", partial_path, operation="create")

        try:
            with zipfile.ZipFile(
                partial_path,
                mode="w",
                compression=zipfile.ZIP_DEFLATED,
                compresslevel=self.compresslevel,
                allowZip64=True,
            ) as archive:
                for index, file_path in enumerate(file_list, start=1):
                    try:
                        arcname = safe_arcname(source_root, file_path)
                        size = self._add_file(archive, file_path, arcname)
                        original_size += size
                        added += 1
                    except Exception as exc:  # noqa: BLE001 — dosya bazlı izolasyon
                        msg = f"{file_path}: {exc}"
                        logger.error("ZIP'e eklenemedi: %s", msg)
                        error_files.append(msg)
                    if progress_callback is not None:
                        progress_callback(index, total, file_path)

            if added == 0 and total > 0:
                detail = "; ".join(error_files[:3]) if error_files else "bilinmeyen neden"
                raise ZipperError(
                    "Hiçbir dosya ZIP'e eklenemedi; yedekleme iptal edildi. "
                    f"Örnek: {detail}"
                )

            verify_zip(partial_path)

            # Atomik nihai ad: aynı dizinde replace
            os.replace(partial_path, final_zip_path)
        except Exception:
            if partial_path.exists():
                try:
                    partial_path.unlink()
                except OSError as cleanup_exc:
                    logger.warning(
                        "Geçici ZIP silinemedi: %s (%s)",
                        partial_path,
                        cleanup_exc,
                    )
            raise

        zip_size = final_zip_path.stat().st_size
        from kurum_yedekleme.utils.formatting import compression_ratio_percent

        ratio = compression_ratio_percent(original_size, zip_size)
        logger.info(
            "ZIP oluşturuldu: %s (dosya=%s, zip=%s bayt, oran=%%%s)",
            final_zip_path,
            added,
            zip_size,
            ratio,
            operation="create",
        )
        return ZipBuildResult(
            zip_path=final_zip_path,
            file_count=added,
            original_size=original_size,
            zip_size=zip_size,
            compression_ratio_percent=ratio,
            skipped_files=skipped_files,
            error_files=error_files,
        )

    def _add_file(
        self,
        archive: zipfile.ZipFile,
        file_path: Path,
        arcname: str,
    ) -> int:
        """
        Tek dosyayı UTF-8 bayraklı ve chunk'lı olarak ZIP'e ekler (streaming).

        Returns:
            Dosya boyutu (bayt).
        """
        st = file_path.stat()
        size = st.st_size
        info = zipfile.ZipInfo(filename=arcname)
        info.compress_type = zipfile.ZIP_DEFLATED
        info.file_size = size
        mtime = datetime.fromtimestamp(st.st_mtime)
        info.date_time = (
            mtime.year,
            mtime.month,
            mtime.day,
            mtime.hour,
            mtime.minute,
            mtime.second,
        )
        _set_utf8_flag(info)

        # Kaynak yalnızca okunur; chunk ile kopyala (büyük dosya → sabit bellek ~chunk_size)
        with _open_source_readonly(file_path) as src, archive.open(
            info, mode="w", force_zip64=size > (1 << 31)
        ) as dest:
            shutil.copyfileobj(src, dest, length=self.chunk_size)
        return size
