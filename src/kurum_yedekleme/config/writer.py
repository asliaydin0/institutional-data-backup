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
    # Kullanılmayan eski anahtarları yazmayın
    for obsolete in (
        "sources",
        "destination",
        "integrity",
        "security",
        "autostart",
    ):
        raw.pop(obsolete, None)
    app = raw.get("app")
    if isinstance(app, dict):
        app.pop("temp_dir", None)
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

    _dump_raw(path, raw)
    logger.info("Uygulama ayarları kaydedildi: %s", path)
    return load_settings(path)


def parse_schedule_config(enabled: bool, time: str) -> ScheduleConfig:
    return ScheduleConfig(
        enabled=bool(enabled),
        time=validate_schedule_time(time),
    )
