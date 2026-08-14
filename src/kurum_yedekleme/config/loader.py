"""Yapılandırma yükleme ve doğrulama."""

from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Any, Optional

import yaml

from kurum_yedekleme.config.schema import (
    DEFAULT_BACKUP_ROOT,
    AppConfig,
    AppSettings,
    LoggingConfig,
    RetryConfig,
    ScheduleConfig,
    ZipConfig,
)
from kurum_yedekleme.utils.paths import get_bundle_root, get_project_root

logger = logging.getLogger(__name__)


class ConfigError(Exception):
    """Yapılandırma okuma veya doğrulama hatası."""


def default_config_path() -> Path:
    return get_project_root() / "config" / "config.yaml"


def example_config_path() -> Path:
    bundled = get_bundle_root() / "config" / "config.example.yaml"
    if bundled.is_file():
        return bundled
    return get_project_root() / "config" / "config.example.yaml"


def ensure_config_file(config_path: Optional[Path] = None) -> Path:
    path = config_path or default_config_path()
    if path.is_file():
        return path

    example = example_config_path()
    if not example.is_file():
        raise ConfigError(
            f"Yapılandırma bulunamadı ve örnek dosya eksik: {example}"
        )

    path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(example, path)
    logger.info("Örnek yapılandırmadan oluşturuldu: %s", path)
    return path


def _require_mapping(data: Any, context: str) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise ConfigError(f"{context} bir nesne (mapping) olmalıdır.")
    return data


def _build_settings(raw: dict[str, Any]) -> AppSettings:
    app_raw = _require_mapping(raw.get("app") or {}, "app")
    schedule_raw = _require_mapping(raw.get("schedule") or {}, "schedule")
    retry_raw = _require_mapping(raw.get("retry") or {}, "retry")
    logging_raw = _require_mapping(raw.get("logging") or {}, "logging")
    zip_raw = _require_mapping(raw.get("zip") or {}, "zip")

    backup_root = str(
        raw.get("backup_root")
        or (raw.get("destination") or {}).get("path")
        or DEFAULT_BACKUP_ROOT
    ).strip()
    if not backup_root:
        raise ConfigError("'backup_root' zorunludur.")

    retry_count = retry_raw.get("max_attempts", retry_raw.get("count", 3))
    retry_delay = retry_raw.get(
        "initial_delay_seconds", retry_raw.get("delay", 10)
    )

    return AppSettings(
        app=AppConfig(
            name=str(app_raw.get("name", "Kurum Yedekleme")),
            language=str(app_raw.get("language", "tr")),
            data_dir=str(app_raw.get("data_dir", "./data")),
            log_dir=str(app_raw.get("log_dir", "./logs")),
        ),
        backup_root=backup_root,
        schedule=ScheduleConfig(
            enabled=bool(schedule_raw.get("enabled", True)),
            time=str(schedule_raw.get("time", "02:00")),
        ),
        retry=RetryConfig(
            max_attempts=int(retry_count),
            initial_delay_seconds=int(retry_delay),
            backoff_multiplier=float(retry_raw.get("backoff_multiplier", 2)),
        ),
        logging=LoggingConfig(
            level=str(logging_raw.get("level", "INFO")),
            rotation=str(logging_raw.get("rotation", "size")).lower(),
            max_bytes=int(logging_raw.get("max_bytes", 5_242_880)),
            backup_count=int(logging_raw.get("backup_count", 10)),
        ),
        zip=ZipConfig(
            compresslevel=int(zip_raw.get("compresslevel", 6)),
            exclude_patterns=list(
                zip_raw.get("exclude_patterns")
                or ["*.tmp", "~$*", "Thumbs.db"]
            ),
        ),
    )


def load_settings(config_path: Optional[Path] = None) -> AppSettings:
    path = ensure_config_file(config_path)
    try:
        with path.open("r", encoding="utf-8") as handle:
            raw = yaml.safe_load(handle) or {}
    except OSError as exc:
        raise ConfigError(f"Yapılandırma okunamadı: {path}") from exc
    except yaml.YAMLError as exc:
        raise ConfigError(f"YAML ayrıştırma hatası: {path}") from exc

    if not isinstance(raw, dict):
        raise ConfigError("Yapılandırma kökü bir nesne olmalıdır.")

    settings = _build_settings(raw)
    logger.debug("Yapılandırma yüklendi: %s", path)
    return settings
