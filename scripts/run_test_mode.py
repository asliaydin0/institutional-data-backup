"""
TEST MODE — headless tam yedekleme akışı.

Yalnızca tests/test_data kullanır. Gerçek kurum verilerine dokunmaz.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def run() -> int:
    from kurum_yedekleme.testing.runner import run_test_mode_backup

    ok, report = run_test_mode_backup(project_root=ROOT, force_regenerate=True)
    print(report)
    if ok:
        print("TEST_MODE_OK")
        return 0
    print("TEST_MODE_FAILED")
    return 1


if __name__ == "__main__":
    raise SystemExit(run())
