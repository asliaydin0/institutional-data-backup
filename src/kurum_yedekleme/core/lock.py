"""Süreçler arası yedekleme kilidi (GUI + Windows Service)."""

from __future__ import annotations

import os
from pathlib import Path
from types import TracebackType
from typing import Optional


class BackupInProgressError(RuntimeError):
    """Aynı anda yalnızca bir yedekleme çalışabilir."""


class BackupLock:
    """
    data/backup.lock üzerinde exclusive kilit.

    GUI ve servis aynı dosyayı kullanır; ikinci işlem BackupInProgressError alır.
    """

    def __init__(self, lock_path: Path) -> None:
        self.lock_path = Path(lock_path)
        self._handle = None

    @property
    def held(self) -> bool:
        return self._handle is not None

    def acquire(self, *, blocking: bool = False) -> None:
        if self._handle is not None:
            return
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        handle = open(self.lock_path, "a+b")
        handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt

                mode = msvcrt.LK_LOCK if blocking else msvcrt.LK_NBLCK
                msvcrt.locking(handle.fileno(), mode, 1)
            else:
                import fcntl

                flags = fcntl.LOCK_EX
                if not blocking:
                    flags |= fcntl.LOCK_NB
                fcntl.flock(handle.fileno(), flags)
            handle.seek(0)
            handle.truncate()
            handle.write(str(os.getpid()).encode("ascii"))
            handle.flush()
            self._handle = handle
        except OSError as exc:
            handle.close()
            raise BackupInProgressError(
                "Şu anda başka bir yedekleme devam ediyor. "
                "Lütfen bitmesini bekleyin."
            ) from exc

    def release(self) -> None:
        handle = self._handle
        if handle is None:
            return
        try:
            handle.seek(0)
            if os.name == "nt":
                import msvcrt

                try:
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                except OSError:
                    pass
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            try:
                handle.close()
            except OSError:
                pass
            self._handle = None

    def __enter__(self) -> "BackupLock":
        self.acquire(blocking=False)
        return self

    def __exit__(
        self,
        exc_type: Optional[type[BaseException]],
        exc: Optional[BaseException],
        tb: Optional[TracebackType],
    ) -> None:
        self.release()
