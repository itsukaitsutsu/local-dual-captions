@echo off
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\Start.ps1" %*
echo.
echo The runner has stopped. If it stopped unexpectedly, run:
echo   powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\Preflight.ps1"
echo.
pause
