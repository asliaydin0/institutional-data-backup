"""Yedekleme sayfası seçimlerinin yenilemede korunması."""

from __future__ import annotations

import os
from datetime import datetime

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from kurum_yedekleme.db.models import BackupArea
from kurum_yedekleme.ui.pages.backup_page import BackupPage


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _area(area_id: int, name: str = "Alan", enabled: bool = True) -> BackupArea:
    now = datetime(2026, 1, 1)
    return BackupArea(
        id=area_id,
        name=name,
        source_path=rf"C:\Kaynak\{name}",
        enabled=enabled,
        deleted=False,
        created_at=now,
        updated_at=now,
    )


def _checked_ids(page: BackupPage) -> set[int]:
    return {
        int(box.property("area_id"))
        for box in page._checks
        if box.isChecked() and box.property("area_id") is not None
    }


def test_refresh_keeps_partial_selection(qapp) -> None:
    page = BackupPage()
    areas = [_area(1, "A"), _area(2, "B"), _area(3, "C")]
    page.set_areas(areas)
    assert _checked_ids(page) == {1, 2, 3}

    page._checks[1].setChecked(False)
    page._checks[2].setChecked(False)
    assert _checked_ids(page) == {1}

    page.set_areas(areas)
    assert _checked_ids(page) == {1}


def test_refresh_keeps_cleared_selection(qapp) -> None:
    page = BackupPage()
    areas = [_area(1, "A"), _area(2, "B")]
    page.set_areas(areas)
    for box in page._checks:
        box.setChecked(False)
    page.set_areas(list(areas))
    assert _checked_ids(page) == set()


def test_same_areas_do_not_rebuild_widgets(qapp) -> None:
    page = BackupPage()
    areas = [_area(1, "A"), _area(2, "B")]
    page.set_areas(areas)
    first_widget = page._checks[0]
    page._checks[0].setChecked(False)
    page.set_areas(areas)
    assert page._checks[0] is first_widget
    assert _checked_ids(page) == {2}


def test_rebuild_preserves_selection_when_area_renamed(qapp) -> None:
    page = BackupPage()
    page.set_areas([_area(1, "A"), _area(2, "B")])
    page._checks[1].setChecked(False)
    page.set_areas([_area(1, "A Yeni"), _area(2, "B")])
    assert _checked_ids(page) == {1}
