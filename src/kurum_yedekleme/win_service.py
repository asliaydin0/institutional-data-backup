"""pywin32 Windows Service sarmalayıcısı."""

from __future__ import annotations

import logging
import sys
import threading
from pathlib import Path

from kurum_yedekleme.services.windows_service import SERVICE_DISPLAY, SERVICE_NAME

logger = logging.getLogger(__name__)

_SERVICE_SCRIPT = Path(__file__).resolve()

# pywin32 SCM kaydı modül seviyesinde import edilebilir sınıf bekler.
KurumYedeklemeWinService = None
_win32serviceutil = None


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


def _ensure_service_class():
    global KurumYedeklemeWinService, _win32serviceutil
    if KurumYedeklemeWinService is not None and _win32serviceutil is not None:
        return KurumYedeklemeWinService, _win32serviceutil

    servicemanager, win32event, win32service, win32serviceutil = _require_pywin32()

    class _KurumYedeklemeWinService(win32serviceutil.ServiceFramework):
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
            servicemanager.LogInfoMsg(f"{SERVICE_NAME} başladı")
            from kurum_yedekleme.service_host import run_service_loop

            run_service_loop(self._stop)
            servicemanager.LogInfoMsg(f"{SERVICE_NAME} durdu")

    KurumYedeklemeWinService = _KurumYedeklemeWinService
    _win32serviceutil = win32serviceutil
    return KurumYedeklemeWinService, win32serviceutil


def install_win32_service() -> None:
    from kurum_yedekleme.services.windows_service import is_user_admin, query_service

    if not is_user_admin():
        raise RuntimeError(
            "Servis kurulumu yönetici yetkisi gerektirir.\n\n"
            "Uygulamayı «Yönetici olarak çalıştır» ile açın veya "
            "Yönetici PowerShell'de scripts\\install_service.ps1 çalıştırın."
        )

    cls, util = _ensure_service_class()
    saved = sys.argv[:]
    try:
        sys.argv = [str(_SERVICE_SCRIPT), "--startup=auto", "install"]
        util.HandleCommandLine(cls)
    finally:
        sys.argv = saved

    status = query_service()
    if status.state == "not_installed":
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

    cls, util = _ensure_service_class()
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
    cls, util = _ensure_service_class()
    util.HandleCommandLine(cls)


if __name__ == "__main__":
    HandleCommandLine()
