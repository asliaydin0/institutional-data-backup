@echo off
setlocal EnableExtensions
cd /d "%~dp0"

REM Debug build: konsol penceresi AÇIK (hata ayıklama)
set "KURUM_YEDEKLEME_DEBUG_BUILD=1"

echo === Kurum Yedekleme — Debug Build (console) ===
call "%~dp0scripts\build_common.bat" debug
exit /b %ERRORLEVEL%
