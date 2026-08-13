@echo off
setlocal EnableExtensions
cd /d "%~dp0.."

set "EXE=dist\KurumYedekleme\KurumYedekleme.exe"
if not exist "%EXE%" (
  echo [HATA] EXE yok. Once build.bat calistirin.
  exit /b 1
)

echo === EXE dogrulama ===
echo EXE: %EXE%
echo.

echo [1] Headless TEST MODE (SQLite + backup engine + test_server)...
"%EXE%" --run-test-backup
if errorlevel 1 (
  echo [HATA] --run-test-backup exit kodu basarisiz
  exit /b 1
)
set "MARKER=dist\KurumYedekleme\data\test_mode_last.txt"
if not exist "%MARKER%" (
  echo [HATA] Marker yok: %MARKER%
  exit /b 1
)
findstr /C:"TEST_MODE_OK" "%MARKER%" >nul
if errorlevel 1 (
  echo [HATA] TEST_MODE_OK marker'da yok
  type "%MARKER%"
  exit /b 1
)
echo [OK] Backup engine + SQLite + aktarim

echo.
echo [2] GUI / tray / SQLite smoke...
.\.venv\Scripts\python.exe scripts\verify_exe_gui.py
if errorlevel 1 (
  echo [HATA] GUI dogrulama basarisiz
  exit /b 1
)

echo.
echo VERIFY_OK
exit /b 0
