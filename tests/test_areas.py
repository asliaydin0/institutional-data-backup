from __future__ import annotations

from pathlib import Path

import pytest

from kurum_yedekleme.services.area_service import AreaError


def test_add_area(runtime, area_source):
    area = runtime.areas.add_area(
        name="Personel", source_path=str(area_source), enabled=True
    )
    assert area.id is not None
    assert area.name == "Personel"
    assert area.enabled is True
    assert area.deleted is False


def test_duplicate_name_rejected(runtime, area_source):
    runtime.areas.add_area(name="Personel", source_path=str(area_source))
    with pytest.raises(AreaError, match="zaten kayıtlı"):
        runtime.areas.add_area(name="Personel", source_path=str(area_source))


def test_edit_area_keeps_id(runtime, area_source, tmp_path):
    area = runtime.areas.add_area(name="Personel", source_path=str(area_source))
    other = tmp_path / "OrtakAlan" / "Personel2"
    other.mkdir(parents=True)
    (other / "x.txt").write_text("x", encoding="utf-8")
    updated = runtime.areas.update_area(
        area.id, name="Personel Birimi", source_path=str(other), enabled=True
    )
    assert updated.id == area.id
    assert updated.name == "Personel Birimi"


def test_soft_delete_keeps_history(runtime, area_source):
    area = runtime.areas.add_area(name="Personel", source_path=str(area_source))
    from kurum_yedekleme.db.models import BackupType

    runtime.backups.run([area], backup_type=BackupType.MANUAL)
    runtime.areas.delete_area(area.id)
    alive = runtime.areas.list_areas()
    assert all(a.id != area.id for a in alive)
    records = runtime.history.get_last_n(10)
    assert any(r.area_name == "Personel" for r in records)
    yedek_root = Path(runtime.settings.backup_root)
    assert any(yedek_root.rglob("*.zip"))


def test_disable_area(runtime, area_source):
    area = runtime.areas.add_area(name="Personel", source_path=str(area_source))
    runtime.areas.set_enabled(area.id, False)
    assert runtime.areas.list_enabled() == []
    assert runtime.areas.get(area.id).enabled is False


def test_multiple_areas(runtime, tmp_path):
    names = ["Helal Akreditasyon", "Personel", "Destek Hizmetleri"]
    for name in names:
        src = tmp_path / "OrtakAlan" / name
        src.mkdir(parents=True)
        (src / "f.txt").write_text(name, encoding="utf-8")
        runtime.areas.add_area(name=name, source_path=str(src))
    enabled = runtime.areas.list_enabled()
    assert len(enabled) == 3


def test_reuse_name_after_soft_delete(runtime, area_source):
    area = runtime.areas.add_area(name="Personel", source_path=str(area_source))
    old_id = area.id
    runtime.areas.delete_area(old_id)
    again = runtime.areas.add_area(name="Personel", source_path=str(area_source))
    assert again.id != old_id


def test_missing_source_rejected(runtime, tmp_path):
    missing = tmp_path / "yok"
    with pytest.raises(AreaError, match="erişilemiyor"):
        runtime.areas.add_area(name="Yok", source_path=str(missing))
