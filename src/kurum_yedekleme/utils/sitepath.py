"""Geliştirme venv'inde src paketini pythonservice.exe'nin de bulması."""

from __future__ import annotations

import sys
from pathlib import Path

from kurum_yedekleme.utils.paths import get_project_root, is_frozen

PTH_NAME = "kurum_yedekleme_src.pth"


def src_root() -> Path:
    return (get_project_root() / "src").resolve()


def ensure_src_pth(prefix: str | Path | None = None) -> Path | None:
    """
    venv site-packages altına src yolunu yazan .pth dosyası oluşturur.

    pythonservice.exe PYTHONPATH kullanmaz; LocalSystem da kullanıcının
    ortam değişkenlerini almaz. .pth, aynı venv'deki her Python sürecinin
    paketi import edebilmesini sağlar.
    """
    if is_frozen():
        return None
    root = Path(prefix or sys.prefix)
    site = root / "Lib" / "site-packages"
    if not site.is_dir():
        return None
    path = site / PTH_NAME
    target = str(src_root())
    current = path.read_text(encoding="utf-8").strip() if path.is_file() else None
    if current != target:
        path.write_text(target + "\n", encoding="utf-8")
    return path
