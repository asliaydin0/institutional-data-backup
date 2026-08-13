"""Windows / UNC yol yardımcıları."""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def is_unc_path(path: str | Path) -> bool:
    """Verilen yolun UNC (\\\\sunucu\\paylasim) olup olmadığını kontrol eder."""
    text = str(path)
    return text.startswith("\\\\") or text.startswith("//")


def normalize_unc(path: str) -> str:
    """UNC yolunda ters eğik çizgileri tutarlı hale getirir."""
    return path.replace("/", "\\")


def to_path(path: str | Path) -> Path:
    """UNC ve yerel yolları Path nesnesine çevirir."""
    if isinstance(path, Path):
        return path
    text = normalize_unc(str(path).strip())
    return Path(text)


def is_path_accessible(path: str | Path) -> bool:
    """Hedef yolun var olup erişilebilir olduğunu kontrol eder."""
    target = to_path(path)
    try:
        return target.exists()
    except OSError as exc:
        logger.warning("Yol erişim kontrolü başarısız: %s (%s)", target, exc)
        return False
