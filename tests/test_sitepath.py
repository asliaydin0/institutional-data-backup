"""venv .pth ile src paket yolunun bağlanması."""

from __future__ import annotations

from pathlib import Path

from kurum_yedekleme.utils import sitepath


def test_ensure_src_pth_writes_src_path(tmp_path: Path, monkeypatch) -> None:
    site = tmp_path / "Lib" / "site-packages"
    site.mkdir(parents=True)
    src = tmp_path / "proj" / "src"
    src.mkdir(parents=True)
    monkeypatch.setattr(sitepath, "is_frozen", lambda: False)
    monkeypatch.setattr(sitepath, "get_project_root", lambda: tmp_path / "proj")

    written = sitepath.ensure_src_pth(tmp_path)
    assert written is not None
    assert written.read_text(encoding="utf-8").strip() == str(src.resolve())

    sitepath.ensure_src_pth(tmp_path)
    assert written.read_text(encoding="utf-8").strip() == str(src.resolve())


def test_ensure_src_pth_skipped_when_frozen(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(sitepath, "is_frozen", lambda: True)
    assert sitepath.ensure_src_pth(tmp_path) is None
