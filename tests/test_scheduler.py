from __future__ import annotations

import time
from datetime import datetime

from kurum_yedekleme.config.schema import ScheduleConfig
from kurum_yedekleme.db.models import BackupStatus, BackupType
from kurum_yedekleme.services.schedule_service import ScheduleService


def test_automatic_skips_if_success_today(runtime, area_source):
    area = runtime.areas.add_area(name="Personel", source_path=str(area_source))
    runtime.backups.run([area], backup_type=BackupType.AUTOMATIC)
    job = runtime.backups.run(
        [area],
        backup_type=BackupType.AUTOMATIC,
        skip_successful_automatic_in_period=True,
    )
    assert job.results == []
    assert any("bu dönemde başarılı" in s for s in job.skipped)


def test_missed_backup_runs_pending(runtime, area_source):
    runtime.areas.add_area(name="Personel", source_path=str(area_source))
    runtime.schedule.update_schedule(ScheduleConfig(enabled=True, time="02:00"))
    now = datetime.now().astimezone().replace(hour=8, minute=0, second=0, microsecond=0)
    info = runtime.schedule.check_missed_backup(now=now)
    assert info is not None
    assert info.pending_area_count == 1
    ran = runtime.schedule.run_missed_if_needed(now=now)
    assert ran is True
    last = runtime.history.get_last_by_type(BackupType.AUTOMATIC)
    assert last is not None
    assert last.status == BackupStatus.SUCCESS


def test_missed_backup_before_schedule_time(runtime, area_source):
    runtime.areas.add_area(name="Personel", source_path=str(area_source))
    runtime.schedule.update_schedule(ScheduleConfig(enabled=True, time="22:00"))
    now = datetime.now().astimezone().replace(hour=8, minute=0, second=0, microsecond=0)
    assert runtime.schedule.check_missed_backup(now=now) is None


def test_tick_at_scheduled_minute(runtime, area_source):
    runtime.areas.add_area(name="Personel", source_path=str(area_source))
    runtime.schedule.update_schedule(ScheduleConfig(enabled=True, time="02:00"))
    now = datetime.now().astimezone().replace(hour=2, minute=0, second=5, microsecond=0)
    assert runtime.schedule.tick(now=now) is True
    last = runtime.history.get_last_backup()
    assert last is not None
    assert last.backup_type == BackupType.AUTOMATIC


def test_tick_weekly_on_scheduled_day(runtime, area_source):
    runtime.areas.add_area(name="Personel", source_path=str(area_source))
    weekday = datetime.now().astimezone().weekday()
    runtime.schedule.update_schedule(
        ScheduleConfig(enabled=True, frequency="weekly", time="02:00", weekday=weekday)
    )
    now = datetime.now().astimezone().replace(
        hour=2, minute=0, second=5, microsecond=0
    )
    assert runtime.schedule.tick(now=now) is True
    last = runtime.history.get_last_backup()
    assert last is not None
    assert last.backup_type == BackupType.AUTOMATIC


def test_tick_weekly_skips_other_days(runtime, area_source):
    runtime.areas.add_area(name="Personel", source_path=str(area_source))
    other_day = (datetime.now().astimezone().weekday() + 1) % 7
    runtime.schedule.update_schedule(
        ScheduleConfig(
            enabled=True, frequency="weekly", time="02:00", weekday=other_day
        )
    )
    now = datetime.now().astimezone().replace(
        hour=2, minute=0, second=5, microsecond=0
    )
    assert runtime.schedule.tick(now=now) is False


def test_service_loop_does_not_need_gui(runtime):
    assert runtime.schedule.is_running is False
    runtime.schedule.start()
    assert runtime.schedule.is_running is True
    runtime.schedule.stop()
    assert runtime.schedule.is_running is False


def test_apply_settings_to_runtime_updates_schedule(runtime):
    from kurum_yedekleme.config.schema import AppSettings, ScheduleConfig
    from kurum_yedekleme.service_host import apply_settings_to_runtime

    updated = AppSettings(
        app=runtime.settings.app,
        backup_root=runtime.settings.backup_root,
        schedule=ScheduleConfig(enabled=True, time="11:20"),
        retention=runtime.settings.retention,
        retry=runtime.settings.retry,
        logging=runtime.settings.logging,
        zip=runtime.settings.zip,
    )
    apply_settings_to_runtime(runtime, updated)
    assert runtime.schedule.schedule.enabled is True
    assert runtime.schedule.schedule.time == "11:20"
    assert runtime.settings.schedule.time == "11:20"


def test_update_schedule_runs_missed_while_running(runtime, area_source):
    runtime.areas.add_area(name="Personel", source_path=str(area_source))
    runtime.schedule.start()
    try:
        runtime.schedule.update_schedule(ScheduleConfig(enabled=True, time="00:00"))
        last = None
        deadline = time.time() + 5
        while time.time() < deadline:
            last = runtime.history.get_last_by_type(BackupType.AUTOMATIC)
            if last is not None:
                break
            time.sleep(0.05)
        assert last is not None
        assert last.status == BackupStatus.SUCCESS
        assert last.backup_type == BackupType.AUTOMATIC
    finally:
        runtime.schedule.stop()


def test_schedule_time_change_allows_same_day_rerun(runtime, area_source):
    runtime.areas.add_area(name="Personel", source_path=str(area_source))
    runtime.schedule.update_schedule(ScheduleConfig(enabled=True, time="02:00"))
    now = datetime.now().astimezone().replace(hour=8, minute=0, second=0, microsecond=0)
    assert runtime.schedule.run_missed_if_needed(now=now) is True
    first = runtime.history.get_last_by_type(BackupType.AUTOMATIC)
    assert first is not None
    runtime.schedule.update_schedule(ScheduleConfig(enabled=True, time="08:05"))
    assert runtime.schedule.run_missed_if_needed(now=now.replace(minute=10)) is True
    rows = [
        r
        for r in runtime.history.get_last_n(10)
        if r.backup_type == BackupType.AUTOMATIC and r.status == BackupStatus.SUCCESS
    ]
    assert len(rows) >= 2
