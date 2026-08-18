"""Eski yedek ZIP temizleme yapılandırması."""

from __future__ import annotations

from dataclasses import dataclass

RETENTION_FREQUENCIES = ("daily", "weekly", "monthly")
DEFAULT_RETENTION_FREQUENCY = "weekly"
DEFAULT_RETENTION_TIME = "03:00"
DEFAULT_RETENTION_KEEP_DAYS = 90
DEFAULT_RETENTION_WEEKDAY = 6  # Pazar (datetime.weekday: Pazartesi=0)
DEFAULT_RETENTION_DAY_OF_MONTH = 1

WEEKDAY_LABELS_TR = (
    "Pazartesi",
    "Salı",
    "Çarşamba",
    "Perşembe",
    "Cuma",
    "Cumartesi",
    "Pazar",
)


@dataclass(frozen=True)
class RetentionConfig:
    """Eski ZIP dosyalarını periyodik silme ayarları."""

    enabled: bool = False
    keep_days: int = DEFAULT_RETENTION_KEEP_DAYS
    frequency: str = DEFAULT_RETENTION_FREQUENCY
    time: str = DEFAULT_RETENTION_TIME
    weekday: int = DEFAULT_RETENTION_WEEKDAY
    day_of_month: int = DEFAULT_RETENTION_DAY_OF_MONTH

    @property
    def frequency_label_tr(self) -> str:
        labels = {
            "daily": "Günlük",
            "weekly": "Haftalık",
            "monthly": "Aylık",
        }
        return labels.get(self.frequency, self.frequency)

    @property
    def weekday_label_tr(self) -> str:
        if 0 <= self.weekday < len(WEEKDAY_LABELS_TR):
            return WEEKDAY_LABELS_TR[self.weekday]
        return str(self.weekday)
