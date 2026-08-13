"""Windows otomatik başlatma — Task Scheduler (kullanıcı oturumu, admin yok)."""

from __future__ import annotations

import logging
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional, Sequence

from kurum_yedekleme.utils.paths import get_project_root

logger = logging.getLogger(__name__)

# Yalnızca bu görev adıyla işlem yapılır; başka görevlere / Run anahtarlarına dokunulmaz.
TASK_FOLDER = "KurumYedekleme"
TASK_NAME = "OtomatikBaslat"
FULL_TASK_NAME = f"{TASK_FOLDER}\\{TASK_NAME}"
LAUNCHER_RELATIVE = Path("scripts") / "start_tray.cmd"


class AutostartError(Exception):
    """Otomatik başlatma kurulum / kaldırma hatası."""


@dataclass(frozen=True)
class AutostartPaths:
    project_root: Path
    launcher: Path
    pythonw: Path


Runner = Callable[[Sequence[str]], subprocess.CompletedProcess[str]]


def _default_runner(args: Sequence[str]) -> subprocess.CompletedProcess[str]:
    kwargs = {
        "capture_output": True,
        "text": True,
        "encoding": "utf-8",
        "errors": "replace",
        "check": False,
    }
    if os.name == "nt":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return subprocess.run(list(args), **kwargs)


def resolve_autostart_paths(*, project_root: Optional[Path] = None) -> AutostartPaths:
    root = (project_root or get_project_root()).resolve()
    launcher = (root / LAUNCHER_RELATIVE).resolve()

    from kurum_yedekleme.utils.paths import is_frozen

    if is_frozen():
        py = Path(sys.executable).resolve()
        return AutostartPaths(project_root=root, launcher=launcher, pythonw=py)

    pythonw = (root / ".venv" / "Scripts" / "pythonw.exe").resolve()
    python_exe = (root / ".venv" / "Scripts" / "python.exe").resolve()
    if pythonw.is_file():
        py = pythonw
    elif python_exe.is_file():
        py = python_exe
    else:
        py = Path(sys.executable).resolve()
    _assert_under_project_or_current(py, root)
    return AutostartPaths(project_root=root, launcher=launcher, pythonw=py)


def _assert_under_project_or_current(exe: Path, project_root: Path) -> None:
    if not exe.is_file():
        raise AutostartError(f"Python yürütücüsü bulunamadı: {exe}")
    try:
        exe.resolve().relative_to(project_root)
        return
    except ValueError:
        pass
    if exe.resolve() == Path(sys.executable).resolve():
        return
    raise AutostartError(
        "Güvenlik: otomatik başlatma yalnızca proje .venv veya "
        f"geçerli Python ile kurulabilir. Reddedildi: {exe}"
    )


def ensure_launcher_script(paths: AutostartPaths) -> Path:
    """
    Tray başlatıcı .cmd dosyasını proje içinde oluşturur/günceller.

    Task Scheduler yalnızca bu betiği çağırır (sabit, denetlenebilir yol).
    """
    from kurum_yedekleme.utils.paths import is_frozen

    paths.launcher.parent.mkdir(parents=True, exist_ok=True)

    if is_frozen():
        # Paketlenmiş EXE: doğrudan --tray
        exe = paths.pythonw
        try:
            exe_ref = "%~dp0..\\" + str(exe.relative_to(paths.project_root)).replace(
                "/", "\\"
            )
        except ValueError:
            exe_ref = str(exe)
        content = (
            "@echo off\r\n"
            "REM Kurum Yedekleme — oturum açılışı (EXE / system tray)\r\n"
            "cd /d \"%~dp0..\"\r\n"
            f"start \"\" \"{exe_ref}\" --tray\r\n"
        )
    else:
        try:
            py_rel = paths.pythonw.relative_to(paths.project_root)
            py_ref = "%~dp0..\\" + str(py_rel).replace("/", "\\")
        except ValueError:
            py_ref = str(paths.pythonw)
        content = (
            "@echo off\r\n"
            "REM Kurum Yedekleme — kullanıcı oturum açılışı (system tray)\r\n"
            "REM Bu dosya Task Scheduler tarafından çağrılır; elle düzenlemeyin.\r\n"
            "cd /d \"%~dp0..\"\r\n"
            "set PYTHONPATH=src\r\n"
            f"\"{py_ref}\" -m kurum_yedekleme --tray\r\n"
        )
    paths.launcher.write_text(content, encoding="utf-8")
    logger.info("Tray başlatıcı hazır: %s", paths.launcher)
    return paths.launcher


class TaskSchedulerAutostart:
    """
    Windows Task Scheduler ile kullanıcı oturum açılışında başlatma.

    - Administrator gerektirmez (/RL LIMITED, mevcut kullanıcı)
    - Registry Run anahtarlarını değiştirmez
    - Yalnızca KurumYedekleme\\OtomatikBaslat görevine dokunur
    """

    def __init__(
        self,
        *,
        runner: Optional[Runner] = None,
        project_root: Optional[Path] = None,
    ) -> None:
        self._runner = runner or _default_runner
        self._root = (project_root or get_project_root()).resolve()

    @property
    def task_name(self) -> str:
        return FULL_TASK_NAME

    def is_enabled(self) -> bool:
        result = self._runner(
            ["schtasks", "/Query", "/TN", FULL_TASK_NAME, "/FO", "LIST"]
        )
        if result.returncode != 0:
            return False
        text = ((result.stdout or "") + (result.stderr or "")).lower()
        if "disabled" in text or "devre dışı" in text:
            return False
        return True

    def enable(self) -> None:
        if FULL_TASK_NAME != f"{TASK_FOLDER}\\{TASK_NAME}":
            raise AutostartError("İç güvenlik: görev adı sabiti bozulmuş.")

        paths = resolve_autostart_paths(project_root=self._root)
        launcher = ensure_launcher_script(paths)
        tr = f'"{launcher}"'
        logger.info("Otomatik başlatma görevi kuruluyor: %s → %s", FULL_TASK_NAME, tr)

        # Temiz güncelleme: yalnızca bizim görev adımız
        self._runner(["schtasks", "/Delete", "/TN", FULL_TASK_NAME, "/F"])

        create = self._runner(
            [
                "schtasks",
                "/Create",
                "/TN",
                FULL_TASK_NAME,
                "/TR",
                tr,
                "/SC",
                "ONLOGON",
                "/RL",
                "LIMITED",
                "/F",
            ]
        )
        if create.returncode != 0:
            detail = (create.stderr or create.stdout or "").strip()
            raise AutostartError(
                "Task Scheduler görevi oluşturulamadı (yönetici gerekmez; "
                f"kullanıcı görevleri). Ayrıntı: {detail or create.returncode}"
            )
        logger.info("Otomatik başlatma etkin: %s", FULL_TASK_NAME)

    def disable(self) -> None:
        if not self._task_exists():
            logger.info("Kaldırılacak otomatik başlatma görevi yok.")
            return
        result = self._runner(
            ["schtasks", "/Delete", "/TN", FULL_TASK_NAME, "/F"]
        )
        if result.returncode != 0 and self._task_exists():
            detail = (result.stderr or result.stdout or "").strip()
            raise AutostartError(
                f"Otomatik başlatma görevi silinemedi: {detail or result.returncode}"
            )
        logger.info("Otomatik başlatma kapatıldı: %s", FULL_TASK_NAME)

    def apply(self, enabled: bool) -> None:
        if enabled:
            self.enable()
        else:
            self.disable()

    def _task_exists(self) -> bool:
        result = self._runner(["schtasks", "/Query", "/TN", FULL_TASK_NAME])
        return result.returncode == 0


def sync_autostart(enabled: bool, *, project_root: Optional[Path] = None) -> None:
    """Yapılandırmadan Task Scheduler'ı senkronize eder."""
    if os.name != "nt":
        raise AutostartError("Otomatik başlatma yalnızca Windows'ta desteklenir.")
    TaskSchedulerAutostart(project_root=project_root).apply(enabled)
