"""İnsan okunur boyut / oran biçimlendirme."""

from __future__ import annotations


def format_bytes(num_bytes: int) -> str:
    """Baytı KB/MB/GB cinsinden Türkçe biçimli metne çevirir."""
    if num_bytes < 0:
        num_bytes = 0
    units = ("B", "KB", "MB", "GB", "TB")
    value = float(num_bytes)
    unit_index = 0
    while value >= 1024.0 and unit_index < len(units) - 1:
        value /= 1024.0
        unit_index += 1
    if unit_index == 0:
        return f"{int(value)} {units[unit_index]}"
    return f"{value:.1f} {units[unit_index]}"


def compression_ratio_percent(original_size: int, zip_size: int) -> float:
    """
    Sıkıştırma ile kazanılan oranı yüzde olarak döner.

    Örnek: 2.4 GB → 840 MB ≈ %65 kazanç.
    Orijinal 0 ise 0.0 döner.
    """
    if original_size <= 0:
        return 0.0
    saved = 1.0 - (zip_size / float(original_size))
    return round(max(0.0, saved) * 100.0, 1)
