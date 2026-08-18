from __future__ import annotations

from kurum_yedekleme.db.models import BackupStatus, BackupType
from kurum_yedekleme.services.runtime import build_runtime


def test_stale_running_marked_failed_on_startup(settings, area_source):
    rt = build_runtime(settings, test_mode=True)
    area = rt.areas.add_area(name="Personel", source_path=str(area_source))
    record_id = rt.history.start_run(
        area_id=area.id,
        area_name=area.name,
        backup_type=BackupType.MANUAL,
    )
    assert rt.history._repo.get_by_id(record_id).status == BackupStatus.RUNNING  # noqa: SLF001
    rt.close()

    rt2 = build_runtime(settings, test_mode=True)
    try:
        record = rt2.history._repo.get_by_id(record_id)  # noqa: SLF001
        assert record is not None
        assert record.status == BackupStatus.FAILED
        assert record.completed_at is not None
        assert "beklenmedik" in (record.error_message or "").lower()
    finally:
        rt2.close()
