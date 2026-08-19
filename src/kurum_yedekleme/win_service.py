"""pywin32 Windows Service sarmalayıcısı."""

from __future__ import annotations

import logging
import os
import sys
import threading
from pathlib import Path
from typing import TYPE_CHECKING, Any

# pythonservice.exe PYTHONPATH olmadan çalışır; geliştirme ortamında src'yi ekle.
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SRC_ROOT = _PROJECT_ROOT / "src"
if _SRC_ROOT.is_dir():
    _src = str(_SRC_ROOT)
    if _src not in sys.path:
        sys.path.insert(0, _src)

from kurum_yedekleme.services.windows_service import SERVICE_DISPLAY, SERVICE_NAME
from kurum_yedekleme.utils.paths import get_project_root

logger = logging.getLogger(__name__)

_SERVICE_SCRIPT = Path(__file__).resolve()

if TYPE_CHECKING:
    KurumYedeklemeWinService: Any
else:
    KurumYedeklemeWinService = None


def _require_pywin32():
    try:
        import servicemanager
        import win32event
        import win32service
        import win32serviceutil
    except ImportError as exc:
        raise RuntimeError(
            "Windows Service kurulumu için pywin32 gerekir. "
            "Kurulum: pip install pywin32"
        ) from exc
    return servicemanager, win32event, win32service, win32serviceutil


def _build_service_class():
    servicemanager, win32event, win32service, win32serviceutil = _require_pywin32()

    class KurumYedeklemeWinService(win32serviceutil.ServiceFramework):
        """SCM tarafından import edilebilir olmalı — isim değiştirilmemeli."""

        _svc_name_ = SERVICE_NAME
        _svc_display_name_ = SERVICE_DISPLAY
        _svc_description_ = (
            "Kurum klasörlerini E:\\Yedekler altına günlük ZIP olarak yedekler."
        )

        def __init__(self, args):
            win32serviceutil.ServiceFramework.__init__(self, args)
            self._stop = threading.Event()
            self.hWaitStop = win32event.CreateEvent(None, 0, 0, None)

        def SvcStop(self):
            self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
            self._stop.set()
            win32event.SetEvent(self.hWaitStop)

        def SvcDoRun(self):
            os.chdir(get_project_root())
            servicemanager.LogInfoMsg(f"{SERVICE_NAME} başladı")
            try:
                from kurum_yedekleme.service_host import run_service_loop

                run_service_loop(self._stop)
            except Exception:
                logger.exception("Servis döngüsü hatası")
                servicemanager.LogErrorMsg(
                    f"{SERVICE_NAME} beklenmeyen hata ile durdu"
                )
                raise
            finally:
                servicemanager.LogInfoMsg(f"{SERVICE_NAME} durdu")

    return KurumYedeklemeWinService, win32serviceutil


if sys.platform == "win32":
    try:
        KurumYedeklemeWinService, _win32serviceutil = _build_service_class()
    except RuntimeError:
        _win32serviceutil = None


def _service_util():
    global KurumYedeklemeWinService, _win32serviceutil
    if KurumYedeklemeWinService is None or _win32serviceutil is None:
        KurumYedeklemeWinService, _win32serviceutil = _build_service_class()
    return KurumYedeklemeWinService, _win32serviceutil


def _configure_installed_service() -> None:
    from kurum_yedekleme.utils.sitepath import ensure_src_pth, src_root

    ensure_src_pth()
    _, win32serviceutil = _service_util()
    root = str(get_project_root())
    win32serviceutil.SetServiceCustomOption(SERVICE_NAME, "AppDirectory", root)
    _set_service_pythonpath(src_root())


def _set_service_pythonpath(src: Path) -> None:
    """LocalSystem sürecine PYTHONPATH ver (SCM Environment)."""
    try:
        import win32api
        import win32con
    except ImportError:
        return
    key = win32api.RegCreateKey(
        win32con.HKEY_LOCAL_MACHINE,
        rf"SYSTEM\CurrentControlSet\Services\{SERVICE_NAME}",
    )
    try:
        win32api.RegSetValueEx(
            key,
            "Environment",
            0,
            win32con.REG_MULTI_SZ,
            [f"PYTHONPATH={src}"],
        )
    finally:
        win32api.RegCloseKey(key)


def install_win32_service() -> None:
    from kurum_yedekleme.services.windows_service import is_user_admin, query_service
    from kurum_yedekleme.utils.sitepath import ensure_src_pth

    if not is_user_admin():
        raise RuntimeError(
            "Servis kurulumu yönetici yetkisi gerektirir.\n\n"
            "Uygulamayı «Yönetici olarak çalıştır» ile açın veya "
            "Yönetici PowerShell'de scripts\\install_service.ps1 çalıştırın."
        )

    ensure_src_pth()
    cls, util = _service_util()
    status = query_service()
    command = "update" if status.state != "not_installed" else "install"
    saved = sys.argv[:]
    try:
        sys.argv = [str(_SERVICE_SCRIPT), "--startup=auto", command]
        util.HandleCommandLine(cls)
    finally:
        sys.argv = saved

    _configure_installed_service()

    after = query_service()
    if after.state == "not_installed":
        raise RuntimeError(
            "Servis Windows'a kaydedilemedi.\n\n"
            "Yönetici yetkisi ve pywin32 kurulumunu kontrol edin."
        )
    logger.info("Windows Service kuruldu: %s", SERVICE_NAME)


def remove_win32_service() -> None:
    from kurum_yedekleme.services.windows_service import is_user_admin, query_service

    if not is_user_admin():
        raise RuntimeError(
            "Servis kaldırma işlemi yönetici yetkisi gerektirir."
        )

    status = query_service()
    if status.state == "not_installed":
        return

    cls, util = _service_util()
    saved = sys.argv[:]
    try:
        sys.argv = [str(_SERVICE_SCRIPT), "remove"]
        util.HandleCommandLine(cls)
    finally:
        sys.argv = saved

    after = query_service()
    if after.state != "not_installed":
        raise RuntimeError(
            "Servis kaldırılamadı.\n\n"
            "Yönetici yetkisiyle tekrar deneyin."
        )
    logger.info("Windows Service kaldırıldı: %s", SERVICE_NAME)


def HandleCommandLine() -> None:
    cls, util = _service_util()
    util.HandleCommandLine(cls)


if __name__ == "__main__":
    HandleCommandLine()
