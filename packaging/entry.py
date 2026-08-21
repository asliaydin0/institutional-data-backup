"""PyInstaller giriş noktası."""

from __future__ import annotations

import sys


def main() -> int:
    if "--win-service" in sys.argv[1:]:
        from kurum_yedekleme.win_service import run_from_scm

        run_from_scm()
        return 0
    from kurum_yedekleme.app import main as app_main

    return int(app_main())


if __name__ == "__main__":
    raise SystemExit(main())
