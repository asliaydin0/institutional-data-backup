"""Yapılandırma şema modelleri — yalnızca kullanılan alanlar."""

from __future__ import annotations

from dataclasses import dataclass, field


from kurum_yedekleme.config.retention_schema import RetentionConfig

DEFAULT_BACKUP_ROOT = r"E:\Yedekler"
@dataclass(frozen=True)
class AppConfig:
    name: str = "Kurum Yedekleme"
    language: str = "tr"
    data_dir: str = "./data"
    log_dir: str = "./logs"


@dataclass(frozen=True)
class ScheduleConfig:
    enabled: bool = True
    time: str = "02:00"


@dataclass(frozen=True)
class RetryConfig:
    max_attempts: int = 3
    initial_delay_seconds: int = 10
    backoff_multiplier: float = 2.0


@dataclass(frozen=True)
class LoggingConfig:
    level: str = "INFO"
    rotation: str = "size"
    max_bytes: int = 5_242_880
    backup_count: int = 10


@dataclass(frozen=True)
class ZipConfig:
    compresslevel: int = 6
    exclude_patterns: list[str] = field(
        default_factory=lambda: ["*.tmp", "~$*", "Thumbs.db"]
    )


@dataclass(frozen=True)
class AppSettings:
    """Uygulamanın tüm yapılandırma ayarları.

    Yedekleme alanları SQLite'dadır; YAML'da tutulmaz.
    """

    app: AppConfig = field(default_factory=AppConfig)
    backup_root: str = DEFAULT_BACKUP_ROOT
    schedule: ScheduleConfig = field(default_factory=ScheduleConfig)
    retention: RetentionConfig = field(default_factory=RetentionConfig)
    retry: RetryConfig = field(default_factory=RetryConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    zip: ZipConfig = field(default_factory=ZipConfig)
