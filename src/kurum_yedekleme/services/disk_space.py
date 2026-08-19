"""Disk alanı ve yedek kökü kontrolleri."""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from kurum_yedekleme.utils.formatting import format_bytes

_MARGIN_BYTES = 64 * 1024 * 1024
PRODUCTION_DRIVE = "E:"


class BackupRootError(RuntimeError):
    """Yedek kök klasörü / disk hatası."""


class InsufficientDiskSpaceError(RuntimeError):
    """Yedekleme için disk alanı yetersiz."""


@dataclass(frozen=True)
class DiskSpaceInfo:
    path: Path
    total_bytes: int
    used_bytes: int
    free_bytes: int


def is_e_drive(path: Path | str) -> bool:
    drive = Path(path).drive.upper()
    if drive:
        return drive == PRODUCTION_DRIVE
    text = str(path).replace("/", "\\")
    return text.upper().startswith("E:\\")


def disk_usage_for(path: Path) -> DiskSpaceInfo:
    target = Path(path)
    candidates = [target]
    if not target.exists():
        candidates.append(target.parent)
    if target.drive:
        candidates.append(Path(target.drive + "\\"))
    last_exc: Optional[OSError] = None
    for candidate in candidates:
        try:
            usage = shutil.disk_usage(str(candidate))
            return DiskSpaceInfo(
                path=candidate,
                total_bytes=usage.total,
                used_bytes=usage.used,
                free_bytes=usage.free,
            )
        except OSError as exc:
            last_exc = exc
            continue
    raise OSError(f"Disk alanı okunamadı: {path} ({last_exc})")


def estimate_source_bytes(source_root: Path) -> int:
    root = Path(source_root)
    if not root.is_dir():
        return 0
    total = 0
    for dirpath, _dirs, files in os.walk(root, followlinks=False):
        for name in files:
            path = Path(dirpath) / name
            try:
                if path.is_symlink():
                    continue
                total += path.stat().st_size
            except OSError:
                continue
    return total


def validate_production_backup_root(backup_root: Path | str) -> Path:
    """Yedek kökü boş olamaz ve mutlak yol olmalıdır (herhangi bir sürücü / UNC)."""
    text = str(backup_root).strip()
    if not text:
        raise BackupRootError("Yedek kök klasörü boş olamaz.")
    root = Path(text)
    if not root.is_absolute():
        raise BackupRootError(
            "Yedek kökü tam yol olmalıdır (ör. D:\\Yedekler veya \\\\sunucu\\paylasim)."
            f" Verilen: {text}"
        )
    return root


def ensure_backup_root_writable(backup_root: Path | str) -> Path:
    root = Path(backup_root)
    try:
        root.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise BackupRootError(
            f"Yedek klasörü oluşturulamadı: {root} ({exc})"
        ) from exc
    if not root.is_dir():
        raise BackupRootError(f"Yedek kökü bir klasör değil: {root}")
    probe = root / f".kurum_yedekleme_write_{os.getpid()}.tmp"
    try:
        probe.write_bytes(b"ok")
        probe.unlink()
    except OSError as exc:
        raise BackupRootError(
            f"Yedek klasörüne yazma izni yok: {root} ({exc})"
        ) from exc
    return root


def assert_disk_space(backup_root: Path, needed_bytes: int) -> DiskSpaceInfo:
    needed = max(0, int(needed_bytes)) + _MARGIN_BYTES
    try:
        info = disk_usage_for(backup_root)
    except OSError as exc:
        raise InsufficientDiskSpaceError(
            f"Disk alanı okunamadı: {backup_root} ({exc})"
        ) from exc
    if info.free_bytes < needed:
        raise InsufficientDiskSpaceError(
            "Yeterli disk alanı yok; yedekleme başlatılmadı.\n"
            f"Gerekli (pay dahil): {format_bytes(needed)}\n"
            f"Boş: {format_bytes(info.free_bytes)}\n"
            f"Yol: {backup_root}"
        )
    return info


def can_read_directory(path: Path) -> tuple[bool, str]:
    if not path.exists():
        return False, "klasör yok"
    if not path.is_dir():
        return False, "klasör değil"
    try:
        next(path.iterdir(), None)
        for child in path.rglob("*"):
            if child.is_file() and not child.is_symlink():
                with child.open("rb") as handle:
                    handle.read(1)
                break
        return True, "okunabilir"
    except PermissionError:
        return False, "okuma izni yok"
    except OSError as exc:
        return False, str(exc)
