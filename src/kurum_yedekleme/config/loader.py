"""Yapılandırma yükleme ve doğrulama."""

from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Any, Optional

import yaml

from kurum_yedekleme.config.schema import (
    AppConfig,
    AppSettings,
    AutostartConfig,
    DestinationConfig,
    IntegrityConfig,
    LoggingConfig,
    RetryConfig,
    ScheduleConfig,
    SecurityConfig,
    SourceConfig,
    ZipConfig,
)
from kurum_yedekleme.utils.paths import get_bundle_root, get_project_root

logger = logging.getLogger(__name__)


class ConfigError(Exception):
    """Yapılandırma okuma veya doğrulama hatası."""


def default_config_path() -> Path:
    """Varsayılan config.yaml yolu (yazılabilir kök)."""
    return get_project_root() / "config" / "config.yaml"


def example_config_path() -> Path:
    """Örnek yapılandırma — önce paket içi, sonra yazılabilir kök."""
    bundled = get_bundle_root() / "config" / "config.example.yaml"
    if bundled.is_file():
        return bundled
    return get_project_root() / "config" / "config.example.yaml"


def ensure_config_file(config_path: Optional[Path] = None) -> Path:
    """
    config.yaml yoksa config.example.yaml üzerinden oluşturur.

    Returns:
        Kullanılacak config dosyasının yolu.
    """
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


def _parse_sources(raw: Any) -> list[SourceConfig]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ConfigError("'sources' bir liste olmalıdır.")

    sources: list[SourceConfig] = []
    for index, item in enumerate(raw):
        item_map = _require_mapping(item, f"sources[{index}]")
        source_id = str(item_map.get("id", "")).strip()
        path = str(item_map.get("path", "")).strip()
        if not source_id or not path:
            raise ConfigError(
                f"sources[{index}] için 'id' ve 'path' zorunludur."
            )
        sources.append(
            SourceConfig(
                id=source_id,
                path=path,
                enabled=bool(item_map.get("enabled", True)),
            )
        )
    return sources


def _build_settings(raw: dict[str, Any]) -> AppSettings:
    app_raw = _require_mapping(raw.get("app", {}), "app")
    dest_raw = _require_mapping(raw.get("destination", {}), "destination")
    schedule_raw = _require_mapping(raw.get("schedule", {}), "schedule")
    zip_raw = _require_mapping(raw.get("zip", {}), "zip")
    integrity_raw = _require_mapping(raw.get("integrity", {}), "integrity")
    retry_raw = _require_mapping(raw.get("retry", {}), "retry")
    logging_raw = _require_mapping(raw.get("logging", {}), "logging")
    security_raw = _require_mapping(raw.get("security", {}), "security")
    autostart_raw = _require_mapping(raw.get("autostart", {}), "autostart")

    unc_path = str(dest_raw.get("unc_path", "")).strip()
    if not unc_path:
        raise ConfigError("'destination.unc_path' zorunludur.")

    return AppSettings(
        app=AppConfig(
            name=str(app_raw.get("name", "Kurum Yedekleme")),
            language=str(app_raw.get("language", "tr")),
            data_dir=str(app_raw.get("data_dir", "./data")),
            log_dir=str(app_raw.get("log_dir", "./logs")),
            temp_dir=str(app_raw.get("temp_dir", "./temp")),
        ),
        sources=_parse_sources(raw.get("sources")),
        destination=DestinationConfig(
            unc_path=unc_path,
            filename_pattern=str(
                dest_raw.get(
                    "filename_pattern",
                    "yedek_{date}_{time}_{hostname}.zip",
                )
            ),
            create_subdirs_by_date=bool(
                dest_raw.get("create_subdirs_by_date", True)
            ),
        ),
        schedule=ScheduleConfig(
            enabled=bool(schedule_raw.get("enabled", True)),
            time=str(schedule_raw.get("time", "02:30")),
            days=list(schedule_raw.get("days") or ["mon", "tue", "wed", "thu", "fri"]),
        ),
        zip=ZipConfig(
            compression=str(zip_raw.get("compression", "deflated")),
            compresslevel=int(zip_raw.get("compresslevel", 6)),
            exclude_patterns=list(zip_raw.get("exclude_patterns") or []),
        ),
        integrity=IntegrityConfig(
            algorithm=str(integrity_raw.get("algorithm", "sha256")),
            verify_after_transfer=bool(
                integrity_raw.get("verify_after_transfer", True)
            ),
        ),
        retry=RetryConfig(
            max_attempts=int(retry_raw.get("max_attempts", 3)),
            initial_delay_seconds=int(
                retry_raw.get("initial_delay_seconds", 5)
            ),
            backoff_multiplier=float(
                retry_raw.get("backoff_multiplier", 2)
            ),
            retry_on=list(
                retry_raw.get("retry_on") or ["network", "io", "timeout"]
            ),
        ),
        logging=LoggingConfig(
            level=str(logging_raw.get("level", "INFO")),
            rotation=str(logging_raw.get("rotation", "size")).lower(),
            max_bytes=int(logging_raw.get("max_bytes", 5_242_880)),
            backup_count=int(logging_raw.get("backup_count", 10)),
        ),
        security=SecurityConfig(
            credential_target=security_raw.get("credential_target"),
            read_only_sources=bool(
                security_raw.get("read_only_sources", True)
            ),
        ),
        autostart=AutostartConfig(
            enabled=bool(autostart_raw.get("enabled", False)),
        ),
    )


def load_settings(config_path: Optional[Path] = None) -> AppSettings:
    """
    YAML yapılandırmasını yükler ve AppSettings döner.

    Raises:
        ConfigError: Dosya okunamaz veya şema geçersizse.
    """
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
