"""Paketlenmiş EXE için kısa GUI/tray/SQLite duman kontrolü."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXE = ROOT / "dist" / "KurumYedekleme" / "KurumYedekleme.exe"


def main() -> int:
    if not EXE.is_file():
        print(f"EXE yok: {EXE}")
        return 1

    marker = EXE.parent / "data" / "smoke_gui_ok.txt"
    if marker.exists():
        marker.unlink()

    proc = subprocess.run(
        [str(EXE), "--smoke-gui"],
        cwd=str(EXE.parent),
        timeout=120,
    )
    if proc.returncode != 0:
        print(f"smoke-gui exit={proc.returncode}")
        return proc.returncode

    if not marker.is_file():
        print(f"Marker yok: {marker}")
        return 1
    text = marker.read_text(encoding="utf-8", errors="replace")
    print(text)
    if "SMOKE_GUI_OK" not in text:
        return 1
    if "sqlite=True" not in text.replace(" ", ""):
        # format: sqlite=True
        if "sqlite=True" not in text:
            print("SQLite smoke başarısız")
            return 1
    print("GUI + SQLite smoke OK")
    if "tray_available=True" in text:
        print("System tray OK")
    else:
        print("System tray bu ortamda yok (offscreen/RDP) — atlandı")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except subprocess.TimeoutExpired:
        print("GUI smoke zaman aşımı")
        raise SystemExit(1)
