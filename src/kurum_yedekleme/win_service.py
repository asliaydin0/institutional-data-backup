"""pywin32 Windows Service sarmalayıcısı.

Geliştirme: SCM, venv python.exe + bu .py dosyasını çalıştırır.
EXE (PyInstaller): SCM, KurumYedekleme.exe --win-service çalıştırır.
pythonservice.exe kullanılmaz.
"""

from __future__ import annotations

import logging
import os
import sys
import threading
from pathlib import Path

from kurum_yedekleme.services.windows_service import SERVICE_DISPLAY, SERVICE_NAME
from kurum_yedekleme.utils.paths import get_project_root, is_frozen

logger = logging.getLogger(__name__)

FROZEN_SERVICE_ARG = "--win-service"

if not is_frozen():
    _src_root = get_project_root() / "src"
    if _src_root.is_dir():
        _src = str(_src_root)
        if _src not in sys.path:
            sys.path.insert(0, _src)

_SERVICE_SCRIPT = Path(__file__).resolve()

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


def service_host_executable() -> str:
    """SCM ImagePath yürütücüsü: EXE veya venv python.exe."""
    if is_frozen():
        return str(Path(sys.executable).resolve())
    venv_python = get_project_root() / ".venv" / "Scripts" / "python.exe"
    if venv_python.is_file():
        return str(venv_python)
    return str(Path(sys.executable).resolve())


def service_host_args() -> str:
    """SCM ImagePath argümanları."""
    if is_frozen():
        return FROZEN_SERVICE_ARG
    return f'"{_SERVICE_SCRIPT}"'


def _install_argv0() -> str:
    if is_frozen():
        return service_host_executable()
    return str(_SERVICE_SCRIPT)


def _build_service_class():
    servicemanager, win32event, win32service, win32serviceutil = _require_pywin32()

    class KurumYedeklemeWinService(win32serviceutil.ServiceFramework):
        _svc_name_ = SERVICE_NAME
        _svc_display_name_ = SERVICE_DISPLAY
        _svc_description_ = (
            "Veri Yedekleme Sistemi — kurum klasörlerini ZIP olarak yedekler."
        )
        _exe_name_ = service_host_executable()
        _exe_args_ = service_host_args()

        def __init__(self, args):
            win32serviceutil.ServiceFramework.__init__(self, args)
            self._stop = threading.Event()
            self.hWaitStop = win32event.CreateEvent(None, 0, 0, None)

        def SvcStop(self):
            self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
            self._stop.set()
            win32event.SetEvent(self.hWaitStop)

        def SvcDoRun(self):
            os.chdir(str(get_project_root()))
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

    if is_frozen():
        _set_service_app_directory()
        return
    ensure_src_pth()
    _, win32serviceutil = _service_util()
    win32serviceutil.SetServiceCustomOption(
        SERVICE_NAME, "AppDirectory", str(get_project_root())
    )
    _set_service_pythonpath(src_root())
    _set_pythonclass_file_path()


def _set_pythonclass_file_path() -> None:
    """SCM'nin paketi değil, bu .py dosyasını yüklemesini sağlar (yalnızca venv)."""
    if is_frozen():
        return
    try:
        import win32serviceutil
    except ImportError:
        return
    class_str = os.path.splitext(str(_SERVICE_SCRIPT))[0] + ".KurumYedeklemeWinService"
    win32serviceutil.InstallPythonClassString(class_str, SERVICE_NAME)
    _set_service_app_directory()


def _set_service_app_directory() -> None:
    try:
        import win32api
        import win32con
    except ImportError:
        return
    key = win32api.RegCreateKey(
        win32con.HKEY_LOCAL_MACHINE,
        rf"SYSTEM\CurrentControlSet\Services\{SERVICE_NAME}\Parameters",
    )
    try:
        win32api.RegSetValueEx(
            key, "AppDirectory", 0, win32con.REG_SZ, str(get_project_root())
        )
    finally:
        win32api.RegCloseKey(key)


def _set_service_pythonpath(src: Path) -> None:
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

    if not is_frozen():
        ensure_src_pth()
    cls, util = _service_util()
    status = query_service()
    command = "update" if status.state != "not_installed" else "install"
    saved = sys.argv[:]
    try:
        sys.argv = [_install_argv0(), "--startup=auto", command]
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
        sys.argv = [_install_argv0(), "remove"]
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


def run_from_scm() -> None:
    """Windows SCM bu süreci başlattığında denetleyiciye bağlan."""
    servicemanager, _, _, _ = _require_pywin32()
    cls, _util = _service_util()
    servicemanager.Initialize(SERVICE_NAME, None)
    servicemanager.PrepareToHostSingle(cls)
    servicemanager.StartServiceCtrlDispatcher()


def HandleCommandLine() -> None:
    cls, util = _service_util()
    util.HandleCommandLine(cls)


if __name__ == "__main__":
    # SCM (venv): argv yalnızca bu script. Kurulum: install / remove / update.
    if len(sys.argv) == 1:
        run_from_scm()
    else:
        HandleCommandLine()
