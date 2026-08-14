"""pywin32 Windows Service sarmalayıcısı."""

from __future__ import annotations

import logging
import sys
import threading

from kurum_yedekleme.services.windows_service import SERVICE_DISPLAY, SERVICE_NAME

logger = logging.getLogger(__name__)


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


def _service_class():
    servicemanager, win32event, win32service, win32serviceutil = _require_pywin32()

    class KurumYedeklemeWinService(win32serviceutil.ServiceFramework):
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

    return KurumYedeklemeWinService, win32serviceutil


def install_win32_service() -> None:
    cls, util = _service_class()
    saved = sys.argv[:]
    try:
        sys.argv = [sys.argv[0], "--startup=auto", "install"]
        util.HandleCommandLine(cls)
    finally:
        sys.argv = saved
    logger.info("Windows Service kuruldu: %s", SERVICE_NAME)


def remove_win32_service() -> None:
    cls, util = _service_class()
    saved = sys.argv[:]
    try:
        sys.argv = [sys.argv[0], "remove"]
        util.HandleCommandLine(cls)
    finally:
        sys.argv = saved
    logger.info("Windows Service kaldırıldı: %s", SERVICE_NAME)


def HandleCommandLine() -> None:
    cls, util = _service_class()
    util.HandleCommandLine(cls)
