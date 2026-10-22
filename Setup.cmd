@echo off
setlocal
cd /d "%~dp0"
echo.
echo LOCAL DUAL CAPTIONS - One-time Windows setup
echo.
echo Read START_HERE.html for prerequisites before continuing.
echo 1. Vulkan - AMD, Intel, or supported NVIDIA GPU (default)
echo 2. CUDA   - NVIDIA GPU
echo 3. CPU    - No GPU acceleration
set "BACKEND=Vulkan"
set /p "CHOICE=Choose 1, 2, or 3 [1]: "
if "%CHOICE%"=="2" set "BACKEND=CUDA"
if "%CHOICE%"=="3" set "BACKEND=CPU"
echo.
echo 1. Full large-v3-turbo - 1.5 GiB (default)
echo 2. Q8 turbo - 834 MiB
echo 3. Q5 turbo - 547 MiB
set "MODEL=large-v3-turbo"
set /p "QUALITY=Choose model 1, 2, or 3 [1]: "
if "%QUALITY%"=="2" set "MODEL=large-v3-turbo-q8_0"
if "%QUALITY%"=="3" set "MODEL=large-v3-turbo-q5_0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\Setup.ps1" -Backend %BACKEND% -Model %MODEL%
echo.
pause
