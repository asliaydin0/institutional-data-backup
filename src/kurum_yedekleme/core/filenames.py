"""Windows dosya / klasör adlarını güvenli hale getirme."""

from __future__ import annotations

import re
from datetime import date, datetime
from pathlib import Path

_INVALID_CHARS = set('<>:"/\\|?*')
_RESERVED = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}

# Yedek klasörü: 2026-08-14_11-35-00 veya eski biçim 2026-08-14
BACKUP_FOLDER_RE = re.compile(
    r"^(\d{4}-\d{2}-\d{2})(?:_(\d{2}-\d{2}-\d{2}))?$"
)


def sanitize_filename(name: str, *, fallback: str = "Alan") -> str:
    """Windows'un izin vermediği karakterleri temizler; ZIP ve klasör adı için."""
    text = str(name or "").strip()
    cleaned_chars: list[str] = []
    for char in text:
        if ord(char) < 32 or char in _INVALID_CHARS:
            cleaned_chars.append("_")
        else:
            cleaned_chars.append(char)
    cleaned = "".join(cleaned_chars).strip(" .")
    cleaned = re.sub(r"_+", "_", cleaned).strip("_") or fallback
    stem = Path(cleaned).stem or cleaned
    if stem.upper() in _RESERVED:
        cleaned = f"_{cleaned}"
    return cleaned[:120]


def area_folder_name(area_name: str) -> str:
    """E:\\Yedekler altındaki alan klasörü."""
    return sanitize_filename(area_name)


def backup_timestamp_folder(when: datetime) -> str:
    """Yedek anına göre tarih+saat klasör adı (yerel saat)."""
    local = when.astimezone() if when.tzinfo else when
    return local.strftime("%Y-%m-%d_%H-%M-%S")


def parse_backup_folder_date(name: str) -> date | None:
    """Yedek tarih klasöründen gün bilgisini çıkarır (eski ve yeni biçim)."""
    match = BACKUP_FOLDER_RE.match(name)
    if not match:
        return None
    try:
        return date.fromisoformat(match.group(1))
    except ValueError:
        return None


def zip_stem_for(area_name: str) -> str:
    """ZIP dosya adı (uzantısız)."""
    return sanitize_filename(area_name)


def tmp_name_for(zip_stem: str) -> str:
    """Aynı klasördeki geçici dosya: .Personel.tmp"""
    return f".{zip_stem}.tmp"


def next_zip_path(directory: Path, area_name: str) -> Path:
    """
    ZIP dosya yolu. Klasör zaten benzersiz tarih-saat içerdiğinden
    genelde <Alan>.zip yeterlidir; aynı klasörde çakışma olursa _2, _3...
    """
    directory = Path(directory)
    stem = zip_stem_for(area_name)
    candidate = directory / f"{stem}.zip"
    if not candidate.exists():
        return candidate
    index = 2
    while True:
        candidate = directory / f"{stem}_{index}.zip"
        if not candidate.exists():
            return candidate
        index += 1
