@echo off
setlocal EnableExtensions
cd /d "%~dp0"

REM Release build: konsol penceresi YOK
set "KURUM_YEDEKLEME_DEBUG_BUILD="

echo === Kurum Yedekleme — Release Build ===
call "%~dp0scripts\build_common.bat" release
exit /b %ERRORLEVEL%
