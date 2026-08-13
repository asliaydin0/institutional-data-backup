"""Disk alanı yardımcıları."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass(frozen=True)
class DiskSpaceInfo:
    path: Path
    total_bytes: int
    used_bytes: int
    free_bytes: int

    @property
    def free_ok(self) -> bool:
        return self.free_bytes > 0


def disk_usage_for(path: Path) -> DiskSpaceInfo:
    """
    Yol için disk kullanımı.

    Yol yoksa ebeveyn / kök denenir (UNC dahil).
    """
    target = Path(path)
    candidates = [target]
    if not target.exists():
        candidates.append(target.parent)
    # Windows sürücü kökü
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


def estimate_source_bytes(source_root: Path, *, exclude_names: Optional[set[str]] = None) -> int:
    """Kaynak ağacının yaklaşık toplam boyutu (salt okuma)."""
    root = Path(source_root)
    if not root.is_dir():
        return 0
    skip = exclude_names or set()
    total = 0
    for dirpath, _dirs, files in __import__("os").walk(root, followlinks=False):
        for name in files:
            if name in skip:
                continue
            path = Path(dirpath) / name
            try:
                if path.is_symlink():
                    continue
                total += path.stat().st_size
            except OSError:
                continue
    return total
