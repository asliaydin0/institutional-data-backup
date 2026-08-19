from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path

from kurum_yedekleme.core.retention import purge_old_backups
from kurum_yedekleme.services.retention_scheduler import RetentionScheduler

def test_purge_deletes_old_zip_only(tmp_path: Path):
    root = tmp_path / "Yedekler"
    old_dir = root / "Personel" / "2020-01-01"
    recent_dir = root / "Personel" / date.today().isoformat()
    old_dir.mkdir(parents=True)
    recent_dir.mkdir(parents=True)
    old_zip = old_dir / "Personel.zip"
    recent_zip = recent_dir / "Personel.zip"
    old_zip.write_bytes(b"old")
    recent_zip.write_bytes(b"new")
    (old_dir / ".Personel.tmp").write_bytes(b"tmp")

    result = purge_old_backups(root, keep_days=30, now=datetime.now().astimezone())
    assert result.deleted_files == 1
    assert not old_zip.exists()
    assert recent_zip.exists()
    assert (old_dir / ".Personel.tmp").exists()
    assert old_dir.exists()


def test_purge_keeps_today_when_keep_days_is_one(tmp_path: Path):
    root = tmp_path / "Yedekler"
    today = date.today().isoformat()
    today_dir = root / "Personel" / f"{today}_12-00-00"
    old_dir = root / "Personel" / "2020-01-01"
    today_dir.mkdir(parents=True)
    old_dir.mkdir(parents=True)
    today_zip = today_dir / "Personel.zip"
    old_zip = old_dir / "Personel.zip"
    today_zip.write_bytes(b"new")
    old_zip.write_bytes(b"old")
    result = purge_old_backups(root, keep_days=1, now=datetime.now().astimezone())
    assert today_zip.exists()
    assert not old_zip.exists()
    assert result.kept_files == 1
    assert result.deleted_files == 1


def test_retention_run_records_last_run(runtime, tmp_path):
    from dataclasses import replace

    root = Path(runtime.settings.backup_root)
    old_dir = root / "Personel" / "2020-01-01"
    old_dir.mkdir(parents=True)
    zip_path = old_dir / "Personel.zip"
    zip_path.write_bytes(b"old")
    runtime.retention.update_settings(
        replace(runtime.settings, retention=replace(runtime.settings.retention, enabled=True, keep_days=1))
    )
    result = runtime.retention.run_now(period_key="2026-08-19")
    assert result.deleted_files == 1
    record = runtime.retention.last_run()
    assert record is not None
    assert record.status == "SUCCESS"
    assert record.deleted_files == 1
    assert any("Personel.zip" in p for p in record.deleted_paths)


def test_retention_logger_accepts_operation(runtime):
    runtime.retention.run_now()
    record = runtime.retention.last_run()
    assert record is not None
    assert record.status in {"SUCCESS", "FAILED", "PARTIAL"}


def test_retention_scheduler_weekly_tick(runtime, tmp_path):
    from dataclasses import replace

    settings = replace_settings_retention(
        runtime.settings,
        enabled=True,
        frequency="weekly",
        time="03:00",
        weekday=6,
        keep_days=30,
    )
    runtime.retention.update_settings(settings)
    runtime.retention_scheduler.update_retention(settings.retention)

    root = Path(runtime.settings.backup_root)
    old_dir = root / "Alan" / "2019-06-01"
    old_dir.mkdir(parents=True)
    (old_dir / "Alan.zip").write_bytes(b"x")

    now = datetime.now().astimezone().replace(
        hour=3, minute=0, second=0, microsecond=0
    )
    while now.weekday() != settings.retention.weekday:
        now += timedelta(days=1)

    assert runtime.retention_scheduler.tick(now=now) is True
    assert not (old_dir / "Alan.zip").exists()


def test_retention_run_if_due_once_per_period(runtime):
    from dataclasses import replace

    runtime.retention.update_settings(
        replace(runtime.settings, retention=replace(runtime.settings.retention, enabled=True))
    )
    first = runtime.retention.run_if_due("2026-W34")
    second = runtime.retention.run_if_due("2026-W34")
    assert first is not None
    assert second is None


def test_retention_time_change_allows_same_period_rerun(runtime):
    from dataclasses import replace

    first_settings = replace(
        runtime.settings,
        retention=replace(
            runtime.settings.retention, enabled=True, time="16:02", keep_days=1
        ),
    )
    runtime.retention.update_settings(first_settings)
    first = runtime.retention.run_if_due("2026-08-19")
    assert first is not None
    assert runtime.retention.run_if_due("2026-08-19") is None

    later = replace(
        first_settings,
        retention=replace(first_settings.retention, time="16:20"),
    )
    runtime.retention.update_settings(later)
    assert runtime.retention.last_period_key() is None
    again = runtime.retention.run_if_due("2026-08-19")
    assert again is not None


def test_retention_missed_run_after_time_already_passed(runtime):
    from dataclasses import replace

    settings = replace_settings_retention(
        runtime.settings,
        enabled=True,
        frequency="daily",
        time="16:20",
        keep_days=1,
    )
    runtime.retention.update_settings(settings)
    runtime.retention.run_if_due("2026-08-19")
    runtime.retention.update_settings(
        replace(settings, retention=replace(settings.retention, time="16:25"))
    )
    runtime.retention_scheduler.update_retention(
        runtime.retention.config,
    )
    now = datetime.now().astimezone().replace(
        hour=16, minute=26, second=0, microsecond=0
    )
    assert runtime.retention_scheduler.run_missed_if_needed(now=now) is True


def replace_settings_retention(settings, **kwargs):
    from dataclasses import replace

    return replace(
        settings,
        retention=replace(settings.retention, **kwargs),
    )
