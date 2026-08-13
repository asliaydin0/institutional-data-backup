"""PyInstaller giriş noktası."""

from __future__ import annotations

import sys


def main() -> int:
    from kurum_yedekleme.app import main as app_main

    return int(app_main())


if __name__ == "__main__":
    raise SystemExit(main())
