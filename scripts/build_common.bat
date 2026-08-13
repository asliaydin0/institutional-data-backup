@echo off
setlocal EnableExtensions
cd /d "%~dp0.."

if not exist ".venv\Scripts\python.exe" (
  echo [HATA] .venv bulunamadi. Once: scripts\create_venv.ps1
  exit /b 1
)

set "PY=.venv\Scripts\python.exe"
set "MODE=%~1"
if "%MODE%"=="" set "MODE=release"

echo [1/4] Bagimliliklar...
"%PY%" -m pip install -q -r requirements.txt
if errorlevel 1 exit /b 1

echo [2/4] Ikon...
"%PY%" scripts\generate_icon.py
if errorlevel 1 exit /b 1

echo [3/4] Onceki build temizligi...
if exist "build\pyinstaller" rmdir /s /q "build\pyinstaller"
if exist "dist\KurumYedekleme" rmdir /s /q "dist\KurumYedekleme"

echo [4/4] PyInstaller (%MODE%)...
set "PYTHONPATH=src"
"%PY%" -m PyInstaller ^
  --noconfirm ^
  --clean ^
  --distpath dist ^
  --workpath build\pyinstaller ^
  packaging\KurumYedekleme.spec

if errorlevel 1 (
  echo [HATA] Build basarisiz.
  exit /b 1
)

echo.
echo Build tamam: dist\KurumYedekleme\KurumYedekleme.exe
if /i "%MODE%"=="debug" (
  echo Mod: DEBUG ^(console acik^)
) else (
  echo Mod: RELEASE ^(console kapali^)
)
exit /b 0
