"""Güvenli ZIP oluşturma — kaynaklar yalnızca okunur; hedefte .tmp → .zip."""

from __future__ import annotations

import fnmatch
import os
import shutil
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional, Sequence

from kurum_yedekleme.core.filenames import tmp_name_for
from kurum_yedekleme.utils.app_logger import get_logger

logger = get_logger("ZipEngine")

ProgressCallback = Callable[[int, int, Path], None]


class ZipperError(Exception):
    """ZIP oluşturma hatası."""


class BackupCancelledError(ZipperError):
    """Kullanıcı iptali."""


@dataclass
class ZipBuildResult:
    zip_path: Path
    file_count: int
    original_size: int
    zip_size: int
    skipped_files: list[str] = field(default_factory=list)
    error_files: list[str] = field(default_factory=list)


def _matches_exclude(name: str, patterns: Sequence[str]) -> bool:
    return any(fnmatch.fnmatch(name, pattern) for pattern in patterns)


def iter_source_files(
    source_root: Path,
    exclude_patterns: Sequence[str] | None = None,
) -> list[Path]:
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
    info.flag_bits |= 0x800


def _open_source_readonly(path: Path):
    return open(path, "rb")  # noqa: SIM115


def validate_zip_central_directory(zip_path: Path) -> None:
    """Merkezi dizini okur — tam içerik taraması (testzip) yapmaz."""
    try:
        with zipfile.ZipFile(zip_path, mode="r") as archive:
            _ = archive.namelist()
    except zipfile.BadZipFile as exc:
        raise ZipperError(f"ZIP bozuk veya okunamıyor: {zip_path}") from exc


def cleanup_orphan_tmps(root: Path) -> int:
    """Hedef ağaçtaki orphan .*.tmp dosyalarını siler. Kaynağa dokunmaz."""
    root = Path(root)
    if not root.is_dir():
        return 0
    removed = 0
    try:
        for tmp in root.rglob("*.tmp"):
            if not tmp.name.startswith("."):
                continue
            try:
                tmp.unlink()
                removed += 1
                logger.info("Orphan tmp silindi: %s", tmp, operation="cleanup")
            except OSError as exc:
                logger.warning("Orphan tmp silinemedi: %s (%s)", tmp, exc)
    except OSError:
        pass
    return removed


class Zipper:
    """Kaynak klasörden salt-okunur ZIP; yarım dosya yalnızca .tmp adında."""

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
        cancel_check: Optional[Callable[[], bool]] = None,
    ) -> ZipBuildResult:
        source_root = Path(source_root)
        final_zip_path = Path(final_zip_path)

        if not source_root.exists():
            raise ZipperError(f"Kaynak klasör bulunamadı: {source_root}")
        if not source_root.is_dir():
            raise ZipperError(f"Kaynak bir klasör değil: {source_root}")

        final_zip_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = final_zip_path.parent / tmp_name_for(final_zip_path.stem)
        if tmp_path.exists():
            tmp_path.unlink()

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

        logger.info("ZIP oluşturuluyor (geçici): %s", tmp_path, operation="create")

        try:
            with zipfile.ZipFile(
                tmp_path,
                mode="w",
                compression=zipfile.ZIP_DEFLATED,
                compresslevel=self.compresslevel,
                allowZip64=True,
            ) as archive:
                for index, file_path in enumerate(file_list, start=1):
                    if cancel_check is not None and cancel_check():
                        raise BackupCancelledError("Yedekleme iptal edildi.")
                    try:
                        arcname = safe_arcname(source_root, file_path)
                        size = self._add_file(archive, file_path, arcname)
                        original_size += size
                        added += 1
                    except BackupCancelledError:
                        raise
                    except Exception as exc:  # noqa: BLE001
                        msg = f"{file_path}: {exc}"
                        logger.error("ZIP'e eklenemedi: %s", msg)
                        error_files.append(msg)
                    if progress_callback is not None:
                        progress_callback(index, total, file_path)

            if cancel_check is not None and cancel_check():
                raise BackupCancelledError("Yedekleme iptal edildi.")

            if added == 0 and total > 0:
                detail = "; ".join(error_files[:3]) if error_files else "bilinmeyen neden"
                raise ZipperError(
                    "Hiçbir dosya ZIP'e eklenemedi; yedekleme iptal edildi. "
                    f"Örnek: {detail}"
                )

            validate_zip_central_directory(tmp_path)
            os.replace(tmp_path, final_zip_path)
        except Exception:
            if tmp_path.exists():
                try:
                    tmp_path.unlink()
                except OSError as cleanup_exc:
                    logger.warning(
                        "Geçici ZIP silinemedi: %s (%s)",
                        tmp_path,
                        cleanup_exc,
                    )
            raise

        zip_size = final_zip_path.stat().st_size
        logger.info(
            "ZIP oluşturuldu: %s (dosya=%s, zip=%s bayt)",
            final_zip_path,
            added,
            zip_size,
            operation="create",
        )
        return ZipBuildResult(
            zip_path=final_zip_path,
            file_count=added,
            original_size=original_size,
            zip_size=zip_size,
            skipped_files=skipped_files,
            error_files=error_files,
        )

    def _add_file(
        self,
        archive: zipfile.ZipFile,
        file_path: Path,
        arcname: str,
    ) -> int:
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

        with _open_source_readonly(file_path) as src, archive.open(
            info, mode="w", force_zip64=size > (1 << 31)
        ) as dest:
            shutil.copyfileobj(src, dest, length=self.chunk_size)
        return size
