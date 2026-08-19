"""Güvenli TEST MODE — gerçek kurum yollarına asla yazılmaz / okunmaz."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

from kurum_yedekleme.config.schema import (
    AppConfig,
    AppSettings,
    LoggingConfig,
    RetryConfig,
    ScheduleConfig,
    ZipConfig,
)
from kurum_yedekleme.utils.paths import get_project_root

TEST_DATA_REL = Path("tests") / "test_data"
SOURCE_REL = TEST_DATA_REL / "source"
DATA_REL = TEST_DATA_REL / "data"
LOG_REL = TEST_DATA_REL / "logs"
YEDEKLER_REL = TEST_DATA_REL / "yedekler"

TEST_AREA_NAMES = (
    "Helal Akreditasyon",
    "Personel",
    "Destek Hizmetleri",
)


class TestModeError(Exception):
    __test__ = False


@dataclass(frozen=True)
class TestModePaths:
    project_root: Path
    test_data: Path
    source: Path
    data: Path
    logs: Path
    yedekler: Path

    __test__ = False


def resolve_test_paths(project_root: Optional[Path] = None) -> TestModePaths:
    root = (project_root or get_project_root()).resolve()
    return TestModePaths(
        project_root=root,
        test_data=(root / TEST_DATA_REL).resolve(),
        source=(root / SOURCE_REL).resolve(),
        data=(root / DATA_REL).resolve(),
        logs=(root / LOG_REL).resolve(),
        yedekler=(root / YEDEKLER_REL).resolve(),
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
    raw = str(path)
    if raw.startswith("\\\\") or raw.startswith("//"):
        raise TestModeError(
            f"TEST MODE güvenlik: {label} UNC/ağ yolu olamaz: {raw}"
        )
    resolved = Path(path).resolve()
    if not any(_is_under(resolved, Path(r)) for r in allowed_roots):
        raise TestModeError(
            f"TEST MODE güvenlik: {label} izinli kök dışında: {resolved}."
        )
    return resolved


def validate_test_settings(settings: AppSettings, paths: TestModePaths) -> None:
    allowed = (paths.test_data,)
    assert_safe_test_path(settings.app.data_dir, allowed_roots=allowed, label="data_dir")
    assert_safe_test_path(settings.app.log_dir, allowed_roots=allowed, label="log_dir")
    assert_safe_test_path(
        settings.backup_root, allowed_roots=allowed, label="backup_root"
    )


def build_test_settings(project_root: Optional[Path] = None) -> AppSettings:
    paths = resolve_test_paths(project_root)
    settings = AppSettings(
        app=AppConfig(
            name="Veri Yedekleme Sistemi (TEST MODE)",
            language="tr",
            data_dir=str(paths.data),
            log_dir=str(paths.logs),
        ),
        backup_root=str(paths.yedekler),
        schedule=ScheduleConfig(enabled=False, time="03:00"),
        zip=ZipConfig(
            compresslevel=6,
            exclude_patterns=["*.tmp", "~$*", ".test_mode_generated"],
        ),
        retry=RetryConfig(max_attempts=2, initial_delay_seconds=0, backoff_multiplier=1),
        logging=LoggingConfig(
            level="INFO", rotation="size", max_bytes=1_048_576, backup_count=3
        ),
    )
    validate_test_settings(settings, paths)
    return settings


def ensure_test_directories(paths: Optional[TestModePaths] = None) -> TestModePaths:
    p = paths or resolve_test_paths()
    for d in (p.test_data, p.source, p.data, p.logs, p.yedekler):
        d.mkdir(parents=True, exist_ok=True)
    return p


def seed_test_areas(area_service, paths: Optional[TestModePaths] = None) -> list:
    """TEST MODE kaynak alt klasörlerini alan olarak ekler (varsa atlar)."""
    p = paths or resolve_test_paths()
    added = []
    for name in TEST_AREA_NAMES:
        folder = p.source / name
        folder.mkdir(parents=True, exist_ok=True)
        try:
            added.append(
                area_service.add_area(
                    name=name,
                    source_path=str(folder),
                    enabled=True,
                    require_source=True,
                )
            )
        except Exception:
            existing = next(
                (a for a in area_service.list_areas() if a.name.lower() == name.lower()),
                None,
            )
            if existing is not None:
                added.append(existing)
    return added
