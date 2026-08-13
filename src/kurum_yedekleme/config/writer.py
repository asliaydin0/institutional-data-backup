"""Yapılandırma dosyasına güvenli yazma."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Optional, Sequence

import yaml

from kurum_yedekleme.config.loader import (
    ConfigError,
    default_config_path,
    ensure_config_file,
    load_settings,
)
from kurum_yedekleme.config.schema import AppSettings, ScheduleConfig, SourceConfig

logger = logging.getLogger(__name__)

_TIME_RE = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")


def validate_schedule_time(value: str) -> str:
    """HH:MM doğrular; normalize edilmiş metni döner."""
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


def save_schedule(
    *,
    enabled: bool,
    time: str,
    config_path: Optional[Path] = None,
) -> AppSettings:
    """schedule.enabled / schedule.time alanlarını YAML'a yazar."""
    path = ensure_config_file(config_path or default_config_path())
    normalized_time = validate_schedule_time(time)
    raw = _load_raw(path)
    schedule = raw.get("schedule")
    if not isinstance(schedule, dict):
        schedule = {}
        raw["schedule"] = schedule
    schedule["enabled"] = bool(enabled)
    schedule["time"] = normalized_time
    if not schedule.get("days"):
        schedule["days"] = [
            "mon", "tue", "wed", "thu", "fri", "sat", "sun",
        ]
    _dump_raw(path, raw)
    logger.info("Zamanlama kaydedildi: enabled=%s time=%s", enabled, normalized_time)
    return load_settings(path)


def save_runtime_settings(
    *,
    sources: Sequence[SourceConfig],
    destination_unc: str,
    schedule_enabled: bool,
    schedule_time: str,
    retry_max_attempts: int,
    retry_delay_seconds: int,
    zip_compresslevel: int,
    autostart_enabled: bool = False,
    config_path: Optional[Path] = None,
) -> AppSettings:
    """Ayarlar ekranından gelen alanları kalıcı olarak kaydeder."""
    path = ensure_config_file(config_path or default_config_path())
    raw = _load_raw(path)

    dest = str(destination_unc).strip()
    if not dest:
        raise ConfigError("Sunucu / hedef yolu boş olamaz.")
    if retry_max_attempts < 1 or retry_max_attempts > 20:
        raise ConfigError("Retry sayısı 1–20 arasında olmalıdır.")
    if retry_delay_seconds < 0 or retry_delay_seconds > 3600:
        raise ConfigError("Retry bekleme süresi 0–3600 saniye olmalıdır.")
    if zip_compresslevel < 0 or zip_compresslevel > 9:
        raise ConfigError("ZIP sıkıştırma seviyesi 0–9 arasında olmalıdır.")

    normalized_time = validate_schedule_time(schedule_time)
    source_list: list[dict[str, Any]] = []
    for index, source in enumerate(sources):
        src_path = str(source.path).strip()
        src_id = str(source.id).strip() or f"kaynak_{index + 1}"
        if not src_path:
            raise ConfigError(f"Kaynak #{index + 1} yolu boş olamaz.")
        source_list.append(
            {"id": src_id, "path": src_path, "enabled": bool(source.enabled)}
        )
    if not source_list:
        raise ConfigError("En az bir kaynak klasörü tanımlanmalıdır.")

    raw["sources"] = source_list
    destination = raw.get("destination")
    if not isinstance(destination, dict):
        destination = {}
        raw["destination"] = destination
    destination["unc_path"] = dest

    schedule = raw.get("schedule")
    if not isinstance(schedule, dict):
        schedule = {}
        raw["schedule"] = schedule
    schedule["enabled"] = bool(schedule_enabled)
    schedule["time"] = normalized_time
    schedule["days"] = [
        "mon", "tue", "wed", "thu", "fri", "sat", "sun",
    ]

    retry = raw.get("retry")
    if not isinstance(retry, dict):
        retry = {}
        raw["retry"] = retry
    retry["max_attempts"] = int(retry_max_attempts)
    retry["initial_delay_seconds"] = int(retry_delay_seconds)

    zip_cfg = raw.get("zip")
    if not isinstance(zip_cfg, dict):
        zip_cfg = {}
        raw["zip"] = zip_cfg
    zip_cfg["compresslevel"] = int(zip_compresslevel)
    zip_cfg["compression"] = zip_cfg.get("compression") or "deflated"

    autostart = raw.get("autostart")
    if not isinstance(autostart, dict):
        autostart = {}
        raw["autostart"] = autostart
    autostart["enabled"] = bool(autostart_enabled)

    _dump_raw(path, raw)
    logger.info("Uygulama ayarları kaydedildi: %s", path)
    return load_settings(path)


def parse_schedule_config(enabled: bool, time: str) -> ScheduleConfig:
    """Doğrulanmış ScheduleConfig üretir."""
    return ScheduleConfig(
        enabled=bool(enabled),
        time=validate_schedule_time(time),
        days=["mon", "tue", "wed", "thu", "fri", "sat", "sun"],
    )
