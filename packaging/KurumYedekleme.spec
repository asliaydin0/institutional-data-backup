# -*- mode: python ; coding: utf-8 -*-
"""KurumYedekleme PyInstaller spec — release (windowed) / debug (console)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_submodules

SPECDIR = Path(SPEC).resolve().parent
ROOT = SPECDIR.parent
SRC = ROOT / "src"
CONFIG_EXAMPLE = ROOT / "config" / "config.example.yaml"
ICON = ROOT / "resources" / "app.ico"

# build.bat DEBUG=1 ile console açılır
DEBUG = os.environ.get("KURUM_YEDEKLEME_DEBUG_BUILD", "").strip() in {
    "1",
    "true",
    "TRUE",
    "yes",
}

datas = []
binaries = []
hiddenimports = [
    "PySide6.QtCore",
    "PySide6.QtGui",
    "PySide6.QtWidgets",
    "yaml",
    "sqlite3",
    "win32serviceutil",
    "win32service",
    "win32event",
    "win32api",
    "win32con",
    "win32timezone",
    "servicemanager",
    "pywintypes",
    "pythoncom",
    "kurum_yedekleme",
    "kurum_yedekleme.app",
    "kurum_yedekleme.service_host",
    "kurum_yedekleme.win_service",
    "kurum_yedekleme.testing",
    "kurum_yedekleme.testing.runner",
    "kurum_yedekleme.testing.fixtures",
    "kurum_yedekleme.testing.test_mode",
]

# PySide6 eklentileri / Qt DLL
ps_datas, ps_binaries, ps_hidden = collect_all("PySide6")
datas += ps_datas
binaries += ps_binaries
hiddenimports += ps_hidden

# pywin32 — EXE içinden Windows Service kurulumu
try:
    import pywintypes
    import pythoncom

    for _mod in (pywintypes, pythoncom):
        _path = getattr(_mod, "__file__", None)
        if _path:
            binaries.append((str(_path), "."))
except ImportError:
    pass

# Paket alt modülleri
hiddenimports += collect_submodules("kurum_yedekleme")

if CONFIG_EXAMPLE.is_file():
    datas.append((str(CONFIG_EXAMPLE), "config"))

# İsteğe bağlı README parçası
resources_dir = ROOT / "resources"
if resources_dir.is_dir():
    for item in resources_dir.iterdir():
        if item.is_file() and item.suffix.lower() in {".ico", ".png", ".txt"}:
            datas.append((str(item), "resources"))

block_cipher = None

a = Analysis(
    [str(ROOT / "packaging" / "entry.py")],
    pathex=[str(SRC), str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "pytest",
        "tkinter",
        "matplotlib",
        "numpy",
        "pandas",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="KurumYedekleme",
    debug=DEBUG,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=DEBUG,  # release: False → konsol yok; debug: True
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ICON) if ICON.is_file() else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="KurumYedekleme",
)
