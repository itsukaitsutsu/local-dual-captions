@echo off
setlocal
cd /d "%~dp0"

echo.
echo LOCAL DUAL CAPTIONS - one-time setup
echo.
echo 1. Vulkan - AMD, Intel or supported NVIDIA GPU (default)
echo 2. CUDA   - NVIDIA GPU
echo 3. CPU    - no GPU acceleration
set "BACKEND=Vulkan"
set /p "CHOICE=Choose 1, 2 or 3 [1]: "
if "%CHOICE%"=="2" set "BACKEND=CUDA"
if "%CHOICE%"=="3" set "BACKEND=CPU"

echo.
echo Engine: use an official prebuilt whisper-server.exe?
echo 1. Yes - download it (no compiler, no SDK, no winget)  [default]
echo 2. No  - compile from source (needs VS 2022, CMake, Git, Vulkan SDK)
set "ENGINEARG=-Prebuilt"
set /p "ENGINE=Choose 1 or 2 [1]: "
if "%ENGINE%"=="2" set "ENGINEARG="
if /i "%BACKEND%"=="Vulkan" if "%ENGINEARG%"=="-Prebuilt" (
  set "ENGINEARG=-Prebuilt -AddVulkanDll"
  echo    ^(whisper.cpp ships no Vulkan build for Windows, so the official
  echo     ggml-vulkan.dll is added to the prebuilt engine automatically.^)
)

echo.
echo Do you already have ggml-large-v3-turbo.bin on this PC?
echo Paste the full path, or press Enter to download a model now.
set "MODELPATH="
set /p "MODELPATH=Model path (or blank): "
set "MODELARG="
if defined MODELPATH (
  if "%MODELPATH:~-1%"=="\" set "MODELPATH=%MODELPATH:~0,-1%"
  set "MODELARG=-ModelPath "%MODELPATH%""
)

echo.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\Setup.ps1" -Backend %BACKEND% %ENGINEARG% %MODELARG%
echo.
pause
