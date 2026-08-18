from __future__ import annotations

from pathlib import Path

import yaml

from kurum_yedekleme.config.loader import load_settings
from kurum_yedekleme.config.sanitize import find_obsolete_config_keys, sanitize_config_raw


def test_find_obsolete_keys():
    raw = {
        "sources": [{"path": "/x"}],
        "destination": {"unc_path": "\\\\srv\\x"},
        "integrity": {"algorithm": "sha256"},
        "app": {"temp_dir": "/tmp"},
        "schedule": {"days": ["mon"]},
        "backup_root": r"E:\Yedekler",
    }
    keys = find_obsolete_config_keys(raw)
    assert "sources" in keys
    assert "destination" in keys
    assert "integrity" in keys
    assert "app.temp_dir" in keys
    assert "schedule.days" in keys


def test_sanitize_removes_obsolete_keys():
    raw = {
        "sources": [],
        "backup_root": r"E:\Yedekler",
        "schedule": {"enabled": True, "time": "02:00", "days": ["mon"]},
    }
    cleaned = sanitize_config_raw(raw)
    assert "sources" not in cleaned
    assert "days" not in cleaned["schedule"]


def test_load_settings_cleans_legacy_yaml(tmp_path: Path, monkeypatch):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    config_path = config_dir / "config.yaml"
    legacy = {
        "app": {"data_dir": str(tmp_path / "data"), "log_dir": str(tmp_path / "logs")},
        "sources": [{"path": "C:/old"}],
        "destination": {"unc_path": "\\\\localhost\\BackupTest"},
        "integrity": {"algorithm": "sha256"},
        "security": {"credential_target": None},
        "autostart": {"enabled": False},
        "schedule": {"enabled": True, "time": "03:30", "days": ["mon"]},
        "backup_root": r"E:\Yedekler",
    }
    config_path.write_text(yaml.safe_dump(legacy), encoding="utf-8")

    monkeypatch.setattr(
        "kurum_yedekleme.config.loader.default_config_path",
        lambda: config_path,
    )
    monkeypatch.setattr(
        "kurum_yedekleme.config.loader.ensure_config_file",
        lambda path=None: config_path,
    )

    settings = load_settings(config_path)
    assert settings.schedule.time == "03:30"
    assert settings.backup_root == r"E:\Yedekler"

    reloaded = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert "sources" not in reloaded
    assert "destination" not in reloaded
    assert "integrity" not in reloaded
    assert "days" not in reloaded.get("schedule", {})
