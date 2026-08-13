"""Yapılandırma şema modelleri."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class AppConfig:
    name: str = "Kurum Yedekleme"
    language: str = "tr"
    data_dir: str = "./data"
    log_dir: str = "./logs"
    temp_dir: str = "./temp"


@dataclass(frozen=True)
class SourceConfig:
    id: str
    path: str
    enabled: bool = True


@dataclass(frozen=True)
class DestinationConfig:
    unc_path: str
    filename_pattern: str = "yedek_{date}_{time}_{hostname}.zip"
    create_subdirs_by_date: bool = True


@dataclass(frozen=True)
class ScheduleConfig:
    # Varsayılan kapalı: yedekleme yalnızca kullanıcı elle başlatınca çalışır.
    # Günlük otomatik için Ayarlar'dan etkinleştirilir.
    enabled: bool = False
    time: str = "02:30"
    days: list[str] = field(default_factory=lambda: ["mon", "tue", "wed", "thu", "fri"])


@dataclass(frozen=True)
class ZipConfig:
    compression: str = "deflated"
    compresslevel: int = 6
    exclude_patterns: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class IntegrityConfig:
    algorithm: str = "sha256"
    verify_after_transfer: bool = True


@dataclass(frozen=True)
class RetryConfig:
    max_attempts: int = 3
    initial_delay_seconds: int = 5
    backoff_multiplier: float = 2.0
    retry_on: list[str] = field(default_factory=lambda: ["network", "io", "timeout"])


@dataclass(frozen=True)
class LoggingConfig:
    """
    level: INFO / DEBUG / WARNING / ERROR
    rotation: size (dosya boyutu) | daily (gece yarısı)
    max_bytes: size rotasyonunda eşik (byte)
    backup_count: saklanacak eski log dosyası üst sınırı (sınırsız büyüme engeli)
    """

    level: str = "INFO"
    rotation: str = "size"
    max_bytes: int = 5_242_880
    backup_count: int = 10


@dataclass(frozen=True)
class SecurityConfig:
    credential_target: Optional[str] = None
    read_only_sources: bool = True


@dataclass(frozen=True)
class AutostartConfig:
    """Windows oturum açılışında otomatik başlatma (Task Scheduler)."""

    enabled: bool = False


@dataclass(frozen=True)
class AppSettings:
    """Uygulamanın tüm yapılandırma ayarları."""

    app: AppConfig = field(default_factory=AppConfig)
    sources: list[SourceConfig] = field(default_factory=list)
    destination: DestinationConfig = field(
        default_factory=lambda: DestinationConfig(
            unc_path=r"\\SUNUCU\Paylasim\Yedekler"
        )
    )
    schedule: ScheduleConfig = field(default_factory=ScheduleConfig)
    zip: ZipConfig = field(default_factory=ZipConfig)
    integrity: IntegrityConfig = field(default_factory=IntegrityConfig)
    retry: RetryConfig = field(default_factory=RetryConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    security: SecurityConfig = field(default_factory=SecurityConfig)
    autostart: AutostartConfig = field(default_factory=AutostartConfig)
