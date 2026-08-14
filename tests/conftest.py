from __future__ import annotations

from pathlib import Path

import pytest

from kurum_yedekleme.config.schema import AppConfig, AppSettings, RetryConfig, ZipConfig
from kurum_yedekleme.services.runtime import build_runtime


@pytest.fixture
def settings(tmp_path: Path) -> AppSettings:
    return AppSettings(
        app=AppConfig(
            data_dir=str(tmp_path / "data"),
            log_dir=str(tmp_path / "logs"),
        ),
        backup_root=str(tmp_path / "Yedekler"),
        retry=RetryConfig(max_attempts=1, initial_delay_seconds=0),
        zip=ZipConfig(compresslevel=1, exclude_patterns=["*.tmp"]),
    )


@pytest.fixture
def runtime(settings: AppSettings):
    rt = build_runtime(settings, test_mode=True, poll_interval_seconds=60)
    yield rt
    rt.close()


@pytest.fixture
def area_source(tmp_path: Path) -> Path:
    src = tmp_path / "OrtakAlan" / "Personel"
    src.mkdir(parents=True)
    (src / "a.txt").write_text("hello", encoding="utf-8")
    (src / "b.txt").write_text("world", encoding="utf-8")
    return src
