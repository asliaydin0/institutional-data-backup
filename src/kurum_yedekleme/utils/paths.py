"""Proje / paket yolu yardımcıları (geliştirme + PyInstaller)."""

from __future__ import annotations

import sys
from pathlib import Path


def is_frozen() -> bool:
    """PyInstaller (veya benzeri) ile paketlenmiş mi?"""
    return bool(getattr(sys, "frozen", False)) and hasattr(sys, "executable")


def get_project_root() -> Path:
    """
    Yazılabilir uygulama kökü.

    - Geliştirme: depo kökü
    - Frozen: KurumYedekleme.exe'nin bulunduğu klasör
      (config/, data/, logs/ burada oluşturulur)
    """
    if is_frozen():
        return Path(sys.executable).resolve().parent
    # src/kurum_yedekleme/utils/paths.py → üç seviye yukarı
    return Path(__file__).resolve().parents[3]


def get_bundle_root() -> Path:
    """
    Salt okunur paketlenmiş kaynaklar.

    - Geliştirme: depo kökü
    - Frozen: PyInstaller _MEIPASS (config.example, icon, …)
    """
    if is_frozen():
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            return Path(meipass)
        return get_project_root()
    return get_project_root()


def resolve_under_root(relative_or_absolute: str | Path) -> Path:
    """Göreli yolu uygulama köküne göre mutlak Path'e çevirir."""
    path = Path(relative_or_absolute)
    if path.is_absolute():
        return path
    return (get_project_root() / path).resolve()
