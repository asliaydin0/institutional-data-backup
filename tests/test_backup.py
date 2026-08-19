from __future__ import annotations

from pathlib import Path

import pytest

from datetime import date, datetime

from kurum_yedekleme.core.filenames import (
    BACKUP_FOLDER_RE,
    backup_timestamp_folder,
    next_zip_path,
    parse_backup_folder_date,
    sanitize_filename,
)
from kurum_yedekleme.core.lock import BackupInProgressError, BackupLock
from kurum_yedekleme.db.models import BackupStatus, BackupType
from kurum_yedekleme.services.disk_space import (
    BackupRootError,
    InsufficientDiskSpaceError,
    assert_disk_space,
    is_e_drive,
    validate_production_backup_root,
)


def test_sanitize_filename():
    assert sanitize_filename("Helal Akreditasyon") == "Helal Akreditasyon"
    assert ":" not in sanitize_filename('Personel:A/B?*')
    assert sanitize_filename("CON").startswith("_")


def test_backup_timestamp_folder():
    when = datetime(2026, 8, 14, 11, 35, 7, tzinfo=datetime.now().astimezone().tzinfo)
    assert backup_timestamp_folder(when) == "2026-08-14_11-35-07"
    assert parse_backup_folder_date("2026-08-14_11-35-07") == date(2026, 8, 14)
    assert parse_backup_folder_date("2026-08-14") == date(2026, 8, 14)
    assert BACKUP_FOLDER_RE.match("2026-08-14_11-35-07")


def test_next_zip_path(tmp_path: Path):
    first = next_zip_path(tmp_path, "Personel")
    assert first.name == "Personel.zip"
    first.write_bytes(b"x")
    second = next_zip_path(tmp_path, "Personel")
    assert second.name == "Personel_2.zip"


def test_backup_root_must_be_absolute():
    assert is_e_drive(r"E:\Yedekler") is True
    assert is_e_drive(r"C:\Yedekler") is False
    assert validate_production_backup_root(r"C:\Yedekler") == Path(r"C:\Yedekler")
    assert validate_production_backup_root(r"E:\Yedekler") == Path(r"E:\Yedekler")
    with pytest.raises(BackupRootError):
        validate_production_backup_root("Yedekler")
    with pytest.raises(BackupRootError):
        validate_production_backup_root("   ")


def test_disk_space_insufficient(tmp_path: Path):
    root = tmp_path / "Yedekler"
    root.mkdir()
    with pytest.raises(InsufficientDiskSpaceError):
        assert_disk_space(root, needed_bytes=10**18)


def test_backup_creates_area_date_zip(runtime, tmp_path):
    src = tmp_path / "Helal Akreditasyon"
    src.mkdir()
    (src / "belge.txt").write_text("icerik", encoding="utf-8")
    area = runtime.areas.add_area(name="Helal Akreditasyon", source_path=str(src))
    job = runtime.backups.run([area], backup_type=BackupType.MANUAL)
    assert job.success_count == 1
    result = job.results[0]
    assert result.zip_path is not None
    assert result.zip_path.name == "Helal Akreditasyon.zip"
    assert BACKUP_FOLDER_RE.match(result.zip_path.parent.name)
    assert result.zip_path.parent.parent.name == "Helal Akreditasyon"
    assert result.zip_path.is_file()
    tmps = list(Path(runtime.settings.backup_root).rglob("*.tmp"))
    assert tmps == []


def test_manual_second_backup_does_not_overwrite_first(runtime, area_source):
    area = runtime.areas.add_area(name="Personel", source_path=str(area_source))
    runtime.backups.run([area], backup_type=BackupType.MANUAL)
    job = runtime.backups.run([area], backup_type=BackupType.MANUAL)
    zips = sorted(Path(runtime.settings.backup_root).rglob("Personel*.zip"))
    assert len(zips) >= 2
    assert job.results[0].backup_type == BackupType.MANUAL


def test_one_area_failure_does_not_stop_others(runtime, tmp_path):
    ok_src = tmp_path / "Helal"
    ok_src.mkdir()
    (ok_src / "a.txt").write_text("ok", encoding="utf-8")
    bad_src = tmp_path / "Personel"
    bad_src.mkdir()
    (bad_src / "a.txt").write_text("x", encoding="utf-8")
    ok = runtime.areas.add_area(name="Helal Akreditasyon", source_path=str(ok_src))
    bad = runtime.areas.add_area(name="Personel", source_path=str(bad_src))
    # kaynak klasörü sil — backup sırasında yok
    for child in bad_src.iterdir():
        child.unlink()
    bad_src.rmdir()
    job = runtime.backups.run([ok, bad], backup_type=BackupType.MANUAL)
    statuses = {r.area.name: r.status for r in job.results}
    assert statuses["Helal Akreditasyon"] == BackupStatus.SUCCESS
    assert statuses["Personel"] == BackupStatus.FAILED
    records = runtime.history.get_last_n(10)
    assert len(records) >= 2
    assert {r.backup_type for r in records} == {BackupType.MANUAL}


def test_cancel_cleans_tmp(runtime, tmp_path):
    src = tmp_path / "Personel"
    src.mkdir()
    for i in range(80):
        (src / f"f{i}.txt").write_text("x" * 4000, encoding="utf-8")
    area = runtime.areas.add_area(name="Personel", source_path=str(src))

    def _cancel_on_progress(_event) -> None:
        runtime.backups.request_cancel()

    job = runtime.backups.run(
        [area],
        backup_type=BackupType.MANUAL,
        progress_emitter=_cancel_on_progress,
    )
    assert job.results
    assert job.results[0].status == BackupStatus.CANCELLED
    assert list(Path(runtime.settings.backup_root).rglob("*.tmp")) == []
    last = runtime.history.get_last_backup()
    assert last is not None
    assert last.status == BackupStatus.CANCELLED


def test_source_files_unchanged(runtime, area_source):
    before = {
        p: (p.stat().st_mtime_ns, p.stat().st_size, p.read_bytes())
        for p in area_source.rglob("*")
        if p.is_file()
    }
    area = runtime.areas.add_area(name="Personel", source_path=str(area_source))
    runtime.backups.run([area], backup_type=BackupType.MANUAL)
    after = {
        p: (p.stat().st_mtime_ns, p.stat().st_size, p.read_bytes())
        for p in area_source.rglob("*")
        if p.is_file()
    }
    assert before == after


def test_orphan_tmp_cleanup(runtime, tmp_path):
    from kurum_yedekleme.core.zipper import cleanup_orphan_tmps

    root = Path(runtime.settings.backup_root)
    dated = root / "Personel" / "2026-08-14"
    dated.mkdir(parents=True)
    orphan = dated / ".Personel.tmp"
    orphan.write_bytes(b"yarim")
    removed = cleanup_orphan_tmps(root)
    assert removed == 1
    assert not orphan.exists()


def test_cross_process_lock(runtime, tmp_path):
    lock_path = runtime.data_dir / "backup.lock"
    first = BackupLock(lock_path)
    first.acquire()
    second = BackupLock(lock_path)
    with pytest.raises(BackupInProgressError):
        second.acquire()
    first.release()
    second.acquire()
    second.release()


def test_history_has_area_and_type(runtime, area_source):
    area = runtime.areas.add_area(name="Personel", source_path=str(area_source))
    runtime.backups.run([area], backup_type=BackupType.MANUAL)
    rec = runtime.history.get_last_backup()
    assert rec is not None
    assert rec.area_id == area.id
    assert rec.area_name == "Personel"
    assert rec.backup_type == BackupType.MANUAL
    assert rec.file_size > 0
    assert rec.status == BackupStatus.SUCCESS


def test_partial_zip_marked_failed(runtime, area_source, tmp_path):
    from unittest.mock import patch

    from kurum_yedekleme.core.zipper import ZipBuildResult

    area = runtime.areas.add_area(name="Personel", source_path=str(area_source))
    zip_path = tmp_path / "Personel.zip"
    zip_path.write_bytes(b"partial")
    fake = ZipBuildResult(
        zip_path=zip_path,
        file_count=1,
        original_size=100,
        zip_size=50,
        error_files=["locked.txt: Erişim engellendi"],
    )
    with patch.object(
        runtime.backups._engine._zipper,  # noqa: SLF001
        "create_archive",
        return_value=fake,
    ):
        job = runtime.backups.run([area], backup_type=BackupType.MANUAL)
    assert len(job.results) == 1
    assert job.results[0].success is False
    assert job.results[0].status == BackupStatus.FAILED
    rec = runtime.history.get_last_backup()
    assert rec is not None
    assert rec.status == BackupStatus.FAILED
