"""Yapılandırma dosyasına güvenli yazma."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Optional

import yaml

from kurum_yedekleme.config.loader import (
    ConfigError,
    default_config_path,
    ensure_config_file,
    load_settings,
)
from kurum_yedekleme.config.periodic import PERIOD_FREQUENCIES, PeriodicTiming
from kurum_yedekleme.config.retention_schema import RetentionConfig
from kurum_yedekleme.config.sanitize import sanitize_config_raw
from kurum_yedekleme.config.schema import AppSettings, ScheduleConfig

logger = logging.getLogger(__name__)

_TIME_RE = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")


def validate_schedule_time(value: str) -> str:
    text = str(value).strip()
    if not _TIME_RE.match(text):
        raise ConfigError(
            f"Geçersiz yedekleme saati: {value!r}. Beklenen biçim HH:MM (örn. 02:00)."
        )
    return text


def validate_schedule_settings(schedule: ScheduleConfig) -> ScheduleConfig:
    timing = validate_periodic_timing(
        schedule.frequency,
        schedule.time,
        schedule.weekday,
        schedule.day_of_month,
        label="Yedekleme sıklığı",
    )
    return ScheduleConfig(
        enabled=bool(schedule.enabled),
        frequency=timing.frequency,
        time=timing.time,
        weekday=timing.weekday,
        day_of_month=timing.day_of_month,
    )


def validate_periodic_timing(
    frequency: str,
    time_value: str,
    weekday: int,
    day_of_month: int,
    *,
    label: str = "Sıklık",
) -> PeriodicTiming:
    freq = str(frequency or "").strip().lower()
    if freq not in PERIOD_FREQUENCIES:
        raise ConfigError(
            f"Geçersiz {label}: {frequency!r}. "
            f"Beklenen: {', '.join(PERIOD_FREQUENCIES)}"
        )
    time_str = validate_schedule_time(time_value)
    wd = int(weekday)
    if wd < 0 or wd > 6:
        raise ConfigError(
            "Haftanın günü 0 (Pazartesi) – 6 (Pazar) arasında olmalıdır."
        )
    dom = int(day_of_month)
    if dom < 1 or dom > 28:
        raise ConfigError("Ayın günü 1–28 arasında olmalıdır.")
    return PeriodicTiming(
        frequency=freq,
        time=time_str,
        weekday=wd,
        day_of_month=dom,
    )


def validate_retention_settings(retention: RetentionConfig) -> RetentionConfig:
    timing = validate_periodic_timing(
        retention.frequency,
        retention.time,
        retention.weekday,
        retention.day_of_month,
        label="temizlik sıklığı",
    )
    keep = int(retention.keep_days)
    if keep < 1 or keep > 3650:
        raise ConfigError("Saklama süresi 1–3650 gün arasında olmalıdır.")
    return RetentionConfig(
        enabled=bool(retention.enabled),
        keep_days=keep,
        frequency=timing.frequency,
        time=timing.time,
        weekday=timing.weekday,
        day_of_month=timing.day_of_month,
    )


def _load_raw(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            raw = yaml.safe_load(handle) or {}
    except OSError as exc:
        raise ConfigError(f"Yapılandırma okunamadı: {path}") from exc
    except yaml.YAMLError as exc:
        raise ConfigError(f"YAML ayrıştırma hatası: {path}") from exc
    if not isinstance(raw, dict):
        raise ConfigError("Yapılandırma kökü bir nesne olmalıdır.")
    return raw


def _dump_raw(path: Path, raw: dict[str, Any]) -> None:
    raw = sanitize_config_raw(raw)
    try:
        with path.open("w", encoding="utf-8") as handle:
            yaml.safe_dump(
                raw,
                handle,
                allow_unicode=True,
                default_flow_style=False,
                sort_keys=False,
            )
    except OSError as exc:
        raise ConfigError(f"Yapılandırma yazılamadı: {path}") from exc


def save_runtime_settings(
    *,
    backup_root: str,
    schedule_enabled: bool,
    schedule_frequency: str = "daily",
    schedule_time: str,
    schedule_weekday: int = 6,
    schedule_day_of_month: int = 1,
    retention_enabled: bool = False,
    retention_keep_days: int = 90,
    retention_frequency: str = "weekly",
    retention_time: str = "03:00",
    retention_weekday: int = 6,
    retention_day_of_month: int = 1,
    config_path: Optional[Path] = None,
) -> AppSettings:
    path = ensure_config_file(config_path or default_config_path())
    raw = _load_raw(path)

    root = str(backup_root).strip()
    if not root:
        raise ConfigError("Yedek kök klasörü boş olamaz.")

    schedule_cfg = validate_schedule_settings(
        ScheduleConfig(
            enabled=bool(schedule_enabled),
            frequency=str(schedule_frequency).lower(),
            time=schedule_time,
            weekday=int(schedule_weekday),
            day_of_month=int(schedule_day_of_month),
        )
    )
    raw["backup_root"] = root

    schedule = raw.get("schedule")
    if not isinstance(schedule, dict):
        schedule = {}
        raw["schedule"] = schedule
    schedule["enabled"] = schedule_cfg.enabled
    schedule["frequency"] = schedule_cfg.frequency
    schedule["time"] = schedule_cfg.time
    schedule["weekday"] = schedule_cfg.weekday
    schedule["day_of_month"] = schedule_cfg.day_of_month
    schedule.pop("days", None)

    retention_cfg = RetentionConfig(
        enabled=bool(retention_enabled),
        keep_days=int(retention_keep_days),
        frequency=str(retention_frequency).lower(),
        time=retention_time,
        weekday=int(retention_weekday),
        day_of_month=int(retention_day_of_month),
    )
    validate_retention_settings(retention_cfg)
    raw["retention"] = {
        "enabled": retention_cfg.enabled,
        "keep_days": retention_cfg.keep_days,
        "frequency": retention_cfg.frequency,
        "time": retention_cfg.time,
        "weekday": retention_cfg.weekday,
        "day_of_month": retention_cfg.day_of_month,
    }

    _dump_raw(path, raw)
    logger.info("Uygulama ayarları kaydedildi: %s", path)
    return load_settings(path)


def parse_schedule_config(
    enabled: bool,
    time: str,
    *,
    frequency: str = "daily",
    weekday: int = 6,
    day_of_month: int = 1,
) -> ScheduleConfig:
    return validate_schedule_settings(
        ScheduleConfig(
            enabled=bool(enabled),
            frequency=frequency,
            time=time,
            weekday=weekday,
            day_of_month=day_of_month,
        )
    )
