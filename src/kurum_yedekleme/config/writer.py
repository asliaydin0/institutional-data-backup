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
from kurum_yedekleme.config.retention_schema import RETENTION_FREQUENCIES, RetentionConfig
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


def validate_retention_settings(retention: RetentionConfig) -> RetentionConfig:
    freq = str(retention.frequency or "").strip().lower()
    if freq not in RETENTION_FREQUENCIES:
        raise ConfigError(
            f"Geçersiz temizlik sıklığı: {retention.frequency!r}. "
            f"Beklenen: {', '.join(RETENTION_FREQUENCIES)}"
        )
    time_str = validate_schedule_time(retention.time)
    keep = int(retention.keep_days)
    if keep < 1 or keep > 3650:
        raise ConfigError("Saklama süresi 1–3650 gün arasında olmalıdır.")
    weekday = int(retention.weekday)
    if weekday < 0 or weekday > 6:
        raise ConfigError(
            "Haftanın günü 0 (Pazartesi) – 6 (Pazar) arasında olmalıdır."
        )
    day = int(retention.day_of_month)
    if day < 1 or day > 28:
        raise ConfigError("Ayın günü 1–28 arasında olmalıdır (aylık temizlik).")
    return RetentionConfig(
        enabled=bool(retention.enabled),
        keep_days=keep,
        frequency=freq,
        time=time_str,
        weekday=weekday,
        day_of_month=day,
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
    schedule_time: str,
    retry_max_attempts: int,
    retry_delay_seconds: int,
    zip_compresslevel: int = 6,
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
    if retry_max_attempts < 1 or retry_max_attempts > 20:
        raise ConfigError("Retry sayısı 1–20 arasında olmalıdır.")
    if retry_delay_seconds < 0 or retry_delay_seconds > 3600:
        raise ConfigError("Retry bekleme süresi 0–3600 saniye olmalıdır.")
    if zip_compresslevel < 0 or zip_compresslevel > 9:
        raise ConfigError("ZIP sıkıştırma seviyesi 0–9 arasında olmalıdır.")

    normalized_time = validate_schedule_time(schedule_time)
    raw["backup_root"] = root

    schedule = raw.get("schedule")
    if not isinstance(schedule, dict):
        schedule = {}
        raw["schedule"] = schedule
    schedule["enabled"] = bool(schedule_enabled)
    schedule["time"] = normalized_time
    schedule.pop("days", None)

    retry = raw.get("retry")
    if not isinstance(retry, dict):
        retry = {}
        raw["retry"] = retry
    retry["max_attempts"] = int(retry_max_attempts)
    retry["initial_delay_seconds"] = int(retry_delay_seconds)
    retry.pop("count", None)
    retry.pop("delay", None)

    zip_cfg = raw.get("zip")
    if not isinstance(zip_cfg, dict):
        zip_cfg = {}
        raw["zip"] = zip_cfg
    zip_cfg["compresslevel"] = int(zip_compresslevel)

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


def parse_schedule_config(enabled: bool, time: str) -> ScheduleConfig:
    return ScheduleConfig(
        enabled=bool(enabled),
        time=validate_schedule_time(time),
    )
