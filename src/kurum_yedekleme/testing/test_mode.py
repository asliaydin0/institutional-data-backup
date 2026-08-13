"""Güvenli TEST MODE — gerçek kurum yollarına asla yazılmaz / okunmaz."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

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
from kurum_yedekleme.utils.paths import get_project_root

# Proje içi izinli kökler (mutlak, resolve sonrası)
TEST_DATA_REL = Path("tests") / "test_data"
TEST_SERVER_REL = Path("test_server")
SOURCE_REL = TEST_DATA_REL / "source"
TEMP_REL = TEST_DATA_REL / "temp"
DATA_REL = TEST_DATA_REL / "data"
LOG_REL = TEST_DATA_REL / "logs"


class TestModeError(Exception):
    """TEST MODE güvenlik / kurulum hatası."""

    # pytest bu sınıfı test sanmasın
    __test__ = False


@dataclass(frozen=True)
class TestModePaths:
    project_root: Path
    test_data: Path
    source: Path
    temp: Path
    data: Path
    logs: Path
    test_server: Path

    __test__ = False


def resolve_test_paths(project_root: Optional[Path] = None) -> TestModePaths:
    root = (project_root or get_project_root()).resolve()
    return TestModePaths(
        project_root=root,
        test_data=(root / TEST_DATA_REL).resolve(),
        source=(root / SOURCE_REL).resolve(),
        temp=(root / TEMP_REL).resolve(),
        data=(root / DATA_REL).resolve(),
        logs=(root / LOG_REL).resolve(),
        test_server=(root / TEST_SERVER_REL).resolve(),
    )


def _is_under(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def assert_safe_test_path(
    path: Path | str,
    *,
    allowed_roots: Iterable[Path],
    label: str,
) -> Path:
    """
    Yol yalnızca izinli TEST MODE köklerinin altında olmalı.
    UNC / kurum yolları reddedilir.
    """
    raw = str(path)
    if raw.startswith("\\\\") or raw.startswith("//"):
        raise TestModeError(
            f"TEST MODE güvenlik: {label} UNC/ağ yolu olamaz: {raw}"
        )
    resolved = Path(path).resolve()
    # Bilinen kurum test dışı yollar
    blocked_markers = (
        "KurumYedekleme_Test",
        "ORNEK-SUNUCU",
        "Yedekler\\KurumYedek",
    )
    lowered = str(resolved).replace("/", "\\")
    for marker in blocked_markers:
        if marker.lower() in lowered.lower():
            raise TestModeError(
                f"TEST MODE güvenlik: {label} kurum/test dışı yolu içeriyor: {resolved}"
            )

    if not any(_is_under(resolved, Path(r)) for r in allowed_roots):
        raise TestModeError(
            f"TEST MODE güvenlik: {label} izinli kök dışında: {resolved}. "
            f"İzinli: {[str(r) for r in allowed_roots]}"
        )
    return resolved


def validate_test_settings(settings: AppSettings, paths: TestModePaths) -> None:
    """AppSettings'in yalnızca TEST MODE yollarını kullandığını doğrular."""
    allowed = (paths.test_data, paths.test_server)
    assert_safe_test_path(settings.app.data_dir, allowed_roots=allowed, label="data_dir")
    assert_safe_test_path(settings.app.log_dir, allowed_roots=allowed, label="log_dir")
    assert_safe_test_path(settings.app.temp_dir, allowed_roots=allowed, label="temp_dir")
    assert_safe_test_path(
        settings.destination.unc_path,
        allowed_roots=allowed,
        label="destination",
    )
    if not settings.sources:
        raise TestModeError("TEST MODE: en az bir kaynak gerekli")
    for src in settings.sources:
        assert_safe_test_path(src.path, allowed_roots=allowed, label=f"source:{src.id}")
    # Gerçek ağ sunucusu yok
    dest = str(settings.destination.unc_path)
    if dest.startswith("\\\\") or dest.startswith("//"):
        raise TestModeError("TEST MODE: gerçek ağ sunucusu (UNC) yasak")


def build_test_settings(project_root: Optional[Path] = None) -> AppSettings:
    """Yalnızca tests/test_data ve test_server kullanan ayarlar."""
    paths = resolve_test_paths(project_root)
    settings = AppSettings(
        app=AppConfig(
            name="Kurum Yedekleme (TEST MODE)",
            language="tr",
            data_dir=str(paths.data),
            log_dir=str(paths.logs),
            temp_dir=str(paths.temp),
        ),
        sources=[
            SourceConfig(id="test_mode_source", path=str(paths.source), enabled=True),
        ],
        destination=DestinationConfig(
            unc_path=str(paths.test_server),
            filename_pattern="TestYedek_{date}_{time}.zip",
            create_subdirs_by_date=True,
        ),
        schedule=ScheduleConfig(enabled=False, time="03:00"),
        zip=ZipConfig(
            compression="deflated",
            compresslevel=6,
            exclude_patterns=["*.tmp", "~$*", ".test_mode_generated"],
        ),
        integrity=IntegrityConfig(algorithm="sha256", verify_after_transfer=True),
        retry=RetryConfig(
            max_attempts=2,
            initial_delay_seconds=0,
            backoff_multiplier=1,
        ),
        logging=LoggingConfig(level="INFO", rotation="size", max_bytes=1_048_576, backup_count=3),
        security=SecurityConfig(credential_target=None, read_only_sources=True),
        autostart=AutostartConfig(enabled=False),
    )
    validate_test_settings(settings, paths)
    return settings


def ensure_test_directories(paths: Optional[TestModePaths] = None) -> TestModePaths:
    """TEST MODE klasörlerini oluşturur (kurum yollarına dokunmaz)."""
    p = paths or resolve_test_paths()
    for d in (p.test_data, p.source, p.temp, p.data, p.logs, p.test_server):
        d.mkdir(parents=True, exist_ok=True)
    return p
