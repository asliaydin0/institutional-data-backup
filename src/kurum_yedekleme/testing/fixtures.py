"""tests/test_data altında örnek kaynak verisi üretir."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from kurum_yedekleme.testing.test_mode import (
    TEST_AREA_NAMES,
    TestModePaths,
    ensure_test_directories,
    resolve_test_paths,
)

LARGE_FILE_BYTES = 256 * 1024
SMALL_FILE_COUNT = 12


def generate_test_source_data(
    paths: Optional[TestModePaths] = None,
    *,
    force: bool = False,
) -> dict[str, object]:
    p = ensure_test_directories(paths or resolve_test_paths())
    source = p.source
    marker = source.parent / ".test_mode_generated"
    if marker.is_file() and not force and source.is_dir() and any(source.iterdir()):
        files = [f for f in source.rglob("*") if f.is_file()]
        return {
            "source": str(source),
            "file_count": len(files),
            "total_bytes": sum(f.stat().st_size for f in files),
            "regenerated": False,
        }

    if source.exists() and force:
        for child in sorted(source.rglob("*"), reverse=True):
            if child.is_file():
                child.unlink()
            elif child.is_dir():
                try:
                    child.rmdir()
                except OSError:
                    pass
        source.mkdir(parents=True, exist_ok=True)

    for area_name in TEST_AREA_NAMES:
        area_dir = source / area_name
        alt = area_dir / "belgeler"
        alt.mkdir(parents=True, exist_ok=True)
        for i in range(1, SMALL_FILE_COUNT + 1):
            target = alt / f"dosya_{i:03d}.txt" if i % 2 == 0 else area_dir / f"dosya_{i:03d}.txt"
            target.write_text(
                f"{area_name} test #{i}\nğüşiöç\n",
                encoding="utf-8",
            )
        (area_dir / "özet.txt").write_text("Türkçe özet", encoding="utf-8")
        (area_dir / "buyuk.bin").write_bytes(b"Z" * LARGE_FILE_BYTES)

    (source / "Eski Birim").mkdir(parents=True, exist_ok=True)
    (source / "Eski Birim" / "arsiv.txt").write_text("eski", encoding="utf-8")

    marker.write_text("generated_by=kurum_yedekleme.testing.fixtures\n", encoding="utf-8")
    files = [f for f in source.rglob("*") if f.is_file()]
    return {
        "source": str(source),
        "file_count": len(files),
        "total_bytes": sum(f.stat().st_size for f in files),
        "regenerated": True,
    }


def clear_test_runtime(paths: Optional[TestModePaths] = None) -> None:
    p = ensure_test_directories(paths or resolve_test_paths())
    for root in (p.data, p.logs, p.yedekler):
        if not root.exists():
            continue
        for child in sorted(root.rglob("*"), reverse=True):
            try:
                if child.is_file():
                    child.unlink()
                elif child.is_dir():
                    child.rmdir()
            except OSError:
                pass
