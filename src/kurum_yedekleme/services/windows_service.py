"""Windows Service durumu — sc.exe (pywin32 gerekmez)."""

from __future__ import annotations

import logging
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from kurum_yedekleme.utils.paths import get_project_root, is_frozen

logger = logging.getLogger(__name__)

SERVICE_NAME = "KurumYedekleme"
SERVICE_DISPLAY = "Kurum Yedekleme"
ServiceState = Literal["running", "stopped", "not_installed", "unknown"]


@dataclass(frozen=True)
class ServiceStatus:
    state: ServiceState
    detail: str = ""

    @property
    def is_running(self) -> bool:
        return self.state == "running"

    @property
    def label_tr(self) -> str:
        return {
            "running": "Çalışıyor",
            "stopped": "Durduruldu",
            "not_installed": "Kurulu değil",
            "unknown": "Bilinmiyor",
        }[self.state]


def is_user_admin() -> bool:
    if os.name != "nt":
        return False
    try:
        import ctypes

        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except (AttributeError, OSError):
        return False


def _run_sc(args: list[str]) -> subprocess.CompletedProcess[str]:
    kwargs = {
        "capture_output": True,
        "text": True,
        "encoding": "utf-8",
        "errors": "replace",
        "check": False,
    }
    if os.name == "nt":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return subprocess.run(["sc.exe", *args], **kwargs)


def query_service() -> ServiceStatus:
    if os.name != "nt":
        return ServiceStatus("unknown", "Windows değil")
    result = _run_sc(["query", SERVICE_NAME])
    text = f"{result.stdout or ''}\n{result.stderr or ''}"
    lowered = text.lower()
    if result.returncode != 0 and (
        "1060" in text
        or "does not exist" in lowered
        or "belirtilen hizmet" in lowered
        or "mevcut değil" in lowered
    ):
        return ServiceStatus("not_installed", text.strip())
    if "RUNNING" in text or "ÇALIŞIYOR" in text.upper() or "calisiyor" in lowered:
        return ServiceStatus("running", text.strip())
    if "STOPPED" in text or "DURDURULDU" in text.upper() or "durduruldu" in lowered:
        return ServiceStatus("stopped", text.strip())
    if result.returncode != 0:
        return ServiceStatus("unknown", text.strip())
    return ServiceStatus("stopped", text.strip())


def start_service() -> None:
    status = query_service()
    if status.state == "running":
        return
    if status.state == "not_installed":
        raise RuntimeError(
            "Servis kurulu değil. Önce «Servisi Kur» ile yükleyin."
        )
    result = _run_sc(["start", SERVICE_NAME])
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise RuntimeError(f"Servis başlatılamadı: {detail or result.returncode}")


def stop_service() -> None:
    status = query_service()
    if status.state != "running":
        return
    result = _run_sc(["stop", SERVICE_NAME])
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        lowered = detail.lower()
        if "1062" in detail or "not been started" in lowered or "başlatılmadı" in lowered:
            return
        raise RuntimeError(f"Servis durdurulamadı: {detail or result.returncode}")


def service_executable() -> Path:
    if is_frozen():
        exe = Path(sys.executable).resolve()
        sibling = exe.with_name("KurumYedeklemeSvc.exe")
        if sibling.is_file():
            return sibling
        return exe
    root = get_project_root()
    pythonw = root / ".venv" / "Scripts" / "python.exe"
    if pythonw.is_file():
        return pythonw
    return Path(sys.executable).resolve()


def service_bin_path() -> str:
    exe = service_executable()
    if is_frozen():
        return f'"{exe}" --run-service'
    root = get_project_root()
    return f'"{exe}" -m kurum_yedekleme --run-service'
    # PYTHONPATH: Task/service working directory should be project root


def install_via_sc() -> None:
    """
    sc create — binPath --run-service.

    Not: SCM, StartServiceCtrlDispatcher bekler. Production'da pywin32
    sarmalayıcısı (win_service) tercih edilir. Bu yöntem NSSM/WinSW
    alternatifi olarak pywin32 kurulumuna düşer.
    """
    from kurum_yedekleme.win_service import install_win32_service

    install_win32_service()
