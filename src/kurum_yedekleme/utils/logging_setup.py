"""Logging kurulumu — format, rotasyon, hassas veri filtresi."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler, TimedRotatingFileHandler
from pathlib import Path
from typing import Optional, Union

from kurum_yedekleme.config.schema import LoggingConfig
from kurum_yedekleme.utils.app_logger import ensure_record_fields, get_logger
from kurum_yedekleme.utils.log_filter import SensitiveDataFilter

LOG_FILE_NAME = "kurum_yedekleme.log"
SERVICE_LOG_FILE_NAME = "kurum_yedekleme_service.log"
# Eski logların sınırsız büyümesini engelle
MAX_BACKUP_COUNT = 30
DEFAULT_BACKUP_COUNT = 10


class InstitutionalFormatter(logging.Formatter):
    """
    Tarih Saat SEVİYE Modül İşlem - Mesaj

    Örnek:
    2026-08-12 02:00:01 INFO BackupScheduler start - Yedekleme başlatıldı
    """

    def format(self, record: logging.LogRecord) -> str:
        ensure_record_fields(record)
        return super().format(record)


def default_formatter() -> InstitutionalFormatter:
    return InstitutionalFormatter(
        fmt="%(asctime)s %(levelname)s %(component)s %(operation)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def clamp_backup_count(value: int) -> int:
    return max(1, min(int(value), MAX_BACKUP_COUNT))


def resolve_log_file(log_dir: Path) -> Path:
    return Path(log_dir) / LOG_FILE_NAME


class SharedAppendFileHandler(logging.Handler):
    """Her kayıtta dosyayı açıp kapatır; GUI ve servis aynı dosyayı paylaşabilir."""

    def __init__(self, filename: Path) -> None:
        super().__init__()
        self._filename = Path(filename)

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self._filename.parent.mkdir(parents=True, exist_ok=True)
            line = self.format(record) + "\n"
            with open(
                self._filename, "a", encoding="utf-8", errors="replace"
            ) as handle:
                handle.write(line)
        except Exception:
            self.handleError(record)


def _build_file_handler(
    log_file: Path,
    cfg: LoggingConfig,
    formatter: logging.Formatter,
    level: int,
) -> Union[RotatingFileHandler, TimedRotatingFileHandler]:
    backup = clamp_backup_count(cfg.backup_count)
    rotation = (cfg.rotation or "size").strip().lower()

    if rotation == "daily":
        handler: Union[RotatingFileHandler, TimedRotatingFileHandler] = (
            TimedRotatingFileHandler(
                log_file,
                when="midnight",
                interval=1,
                backupCount=backup,
                encoding="utf-8",
                utc=False,
            )
        )
        handler.suffix = "%Y-%m-%d"
    else:
        max_bytes = max(64_000, int(cfg.max_bytes))
        handler = RotatingFileHandler(
            log_file,
            maxBytes=max_bytes,
            backupCount=backup,
            encoding="utf-8",
        )

    handler.setFormatter(formatter)
    handler.setLevel(level)
    handler.addFilter(SensitiveDataFilter())
    return handler


def setup_logging(
    log_dir: Path,
    config: Optional[LoggingConfig] = None,
    *,
    also_console: bool = True,
    file_name: str | None = None,
    mirror_file_name: str | None = None,
) -> Path:
    """
    Uygulama genelinde log sistemini kurar.

    - Klasör: logs/ (çağıranın verdiği log_dir)
    - Rotasyon: size (varsayılan) veya daily
    - backup_count ile eski dosya sayısı sınırlanır
    - Parola / token değerleri maskelenir

    Returns:
        Ana log dosyası yolu.
    """
    cfg = config or LoggingConfig()
    log_dir = Path(log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = Path(log_dir) / (file_name or LOG_FILE_NAME)

    level = getattr(logging, cfg.level.upper(), logging.INFO)
    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(level)

    formatter = default_formatter()
    sensitive = SensitiveDataFilter()

    file_handler = _build_file_handler(log_file, cfg, formatter, level)
    root.addHandler(file_handler)

    if mirror_file_name:
        mirror = Path(log_dir) / mirror_file_name
        if mirror.resolve() != log_file.resolve():
            extra = SharedAppendFileHandler(mirror)
            extra.setFormatter(formatter)
            extra.setLevel(level)
            extra.addFilter(sensitive)
            root.addHandler(extra)

    if also_console:
        console = logging.StreamHandler()
        console.setFormatter(formatter)
        console.setLevel(level)
        console.addFilter(sensitive)
        root.addHandler(console)

    # Kök logger'a da filtre (diğer handler'lar için)
    root.addFilter(sensitive)

    log = get_logger("Logging", operation="setup")
    log.info(
        "Log sistemi hazır: %s (seviye=%s, rotasyon=%s, yedek=%s)",
        log_file,
        cfg.level.upper(),
        (cfg.rotation or "size").lower(),
        clamp_backup_count(cfg.backup_count),
    )
    return log_file
