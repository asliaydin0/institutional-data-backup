"""PyInstaller giriş noktası."""

from __future__ import annotations

import os
import sys
from datetime import datetime
from pathlib import Path


def _prepare_frozen_service() -> None:
    """Windowed EXE'de stdout None olmasın; çalışma dizini EXE klasörü olsun."""
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")
    exe_dir = Path(sys.executable).resolve().parent
    try:
        os.chdir(str(exe_dir))
    except OSError:
        pass
    log_dir = exe_dir / "logs"
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        boot = log_dir / "service_boot.log"
        with boot.open("a", encoding="utf-8") as handle:
            handle.write(
                f"{datetime.now().isoformat(timespec='seconds')} "
                f"--win-service pid={os.getpid()} cwd={os.getcwd()}\n"
            )
    except OSError:
        pass


def main() -> int:
    if "--win-service" in sys.argv[1:]:
        _prepare_frozen_service()
        from kurum_yedekleme.win_service import run_from_scm

        run_from_scm()
        return 0
    from kurum_yedekleme.app import main as app_main

    return int(app_main())


if __name__ == "__main__":
    raise SystemExit(main())
