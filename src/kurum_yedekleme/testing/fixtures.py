"""tests/test_data altında örnek kaynak verisi üretir."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from kurum_yedekleme.testing.test_mode import (
    TestModePaths,
    ensure_test_directories,
    resolve_test_paths,
)

# Büyük dosya boyutu (2 MiB) — repo şişmesin, chunk yolunu yine zorlasın
LARGE_FILE_BYTES = 2 * 1024 * 1024
SMALL_FILE_COUNT = 100


def generate_test_source_data(
    paths: Optional[TestModePaths] = None,
    *,
    force: bool = False,
) -> dict[str, object]:
    """
    tests/test_data/source altına örnek dosyaları yazar.

    Returns:
        Özet istatistik (dosya sayısı, bayt vb.)
    """
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
            "has_empty": any(f.stat().st_size == 0 for f in files),
            "has_large": any(f.stat().st_size >= LARGE_FILE_BYTES for f in files),
            "has_turkish": any(
                any(c in f.name for c in "ğüşıöçĞÜŞİÖÇ") for f in files
            ),
        }

    # Temiz başlangıç (yalnızca test_data/source)
    if source.exists() and force:
        for child in sorted(source.rglob("*"), reverse=True):
            if child.is_file():
                child.unlink()
            elif child.is_dir():
                child.rmdir()
        source.mkdir(parents=True, exist_ok=True)

    # Alt klasörler
    alt = source / "alt_klasor"
    derin = alt / "ikinci_seviye"
    tr_dir = source / "Türkçe_Klasör_ğüşiöç"
    boyutlar = source / "boyutlar"
    for d in (alt, derin, tr_dir, boyutlar):
        d.mkdir(parents=True, exist_ok=True)

    # 100 küçük TXT
    for i in range(1, SMALL_FILE_COUNT + 1):
        name = f"dosya_{i:03d}.txt"
        target = alt / name if i % 2 == 0 else source / name
        target.write_text(
            f"Test dosyası #{i}\nKurum Yedekleme TEST MODE\nİçerik: ğüşiöçĞÜŞİÖÇ\n",
            encoding="utf-8",
        )

    # Türkçe karakterli isimler
    (tr_dir / "rapor_özet_ğüşiöç.txt").write_text("özet içerik", encoding="utf-8")
    (tr_dir / "Çalışanlar_Listesi.txt").write_text("liste", encoding="utf-8")
    (derin / "ıİğĞüÜşŞöÖçÇ_belge.txt").write_text("derin belge", encoding="utf-8")

    # Farklı boyutlar
    (boyutlar / "kucuk_1kb.txt").write_bytes(b"A" * 1024)
    (boyutlar / "orta_50kb.bin").write_bytes(b"B" * (50 * 1024))
    (boyutlar / "bos_dosya.txt").write_bytes(b"")
    (boyutlar / "buyuk_dosya.bin").write_bytes(b"Z" * LARGE_FILE_BYTES)

    # Kökte ek örnek
    (source / "README_TEST.txt").write_text(
        "Bu klasör TEST MODE kaynağıdır. Gerçek kurum verisi değildir.\n",
        encoding="utf-8",
    )

    marker.write_text("generated_by=kurum_yedekleme.testing.fixtures\n", encoding="utf-8")

    files = [f for f in source.rglob("*") if f.is_file()]
    total_bytes = sum(f.stat().st_size for f in files)
    return {
        "source": str(source),
        "file_count": len(files),
        "total_bytes": total_bytes,
        "regenerated": True,
        "has_empty": any(f.stat().st_size == 0 for f in files),
        "has_large": any(f.stat().st_size >= LARGE_FILE_BYTES for f in files),
        "has_turkish": any(
            any(c in f.name for c in "ğüşıöçĞÜŞİÖÇ") for f in files
        ),
    }


def clear_test_runtime(paths: Optional[TestModePaths] = None) -> None:
    """temp / data / logs / test_server çalışma çıktılarını temizler (kaynağa dokunmaz)."""
    p = ensure_test_directories(paths or resolve_test_paths())
    for root in (p.temp, p.data, p.logs, p.test_server):
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
