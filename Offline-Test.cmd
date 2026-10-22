@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Run Setup.cmd first.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m bridge.offline_test
echo.
pause
