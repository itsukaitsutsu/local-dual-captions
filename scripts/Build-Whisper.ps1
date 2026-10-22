[CmdletBinding()]
param(
    [ValidateSet('Vulkan','CUDA','CPU')][string]$Backend = 'Vulkan',
    [string]$WhisperRef = 'v1.9.5'
)
$ErrorActionPreference = 'Stop'
$Root = Split-Path $PSScriptRoot -Parent
$Vendor = Join-Path $Root 'vendor'
$Source = Join-Path $Vendor ('whisper-' + $WhisperRef)
$Build = Join-Path $Source ('build-' + $Backend.ToLowerInvariant())

function Invoke-Checked {
    param([string]$Command, [string[]]$Arguments)
    & $Command @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$Command failed (exit $LASTEXITCODE). See the output above." }
}
foreach ($tool in @('git','cmake')) {
    if (-not (Get-Command $tool -ErrorAction SilentlyContinue)) {
        throw "Missing $tool. Install Git for Windows and CMake, then open a new terminal. See START_HERE.html."
    }
}
# Vulkan shader generation needs the MSVC host tools in PATH even when the
# outer project uses the Visual Studio generator. Import them explicitly.
$VsWhere = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio\Installer\vswhere.exe'
if (-not (Test-Path $VsWhere)) { throw 'Install Visual Studio 2022 Build Tools with Desktop development with C++ and a Windows SDK.' }
$Vs = & $VsWhere -latest -version '[17.0,18.0)' -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
if (-not $Vs) { throw 'Visual Studio 2022 C++ tools were not found. Select Desktop development with C++ in the installer.' }
$DevCmd = Join-Path $Vs 'Common7\Tools\VsDevCmd.bat'
$EnvLines = & $env:ComSpec /s /c "`"`"$DevCmd`" -no_logo -arch=x64 -host_arch=x64 >nul && set`""
foreach ($Line in $EnvLines) {
    if ($Line -match '^([^=]+)=(.*)$') { [Environment]::SetEnvironmentVariable($Matches[1], $Matches[2], 'Process') }
}
if ($LASTEXITCODE -ne 0) { throw 'Could not initialize the Visual Studio x64 build environment.' }

New-Item -ItemType Directory -Path $Vendor -Force | Out-Null
if (-not (Test-Path (Join-Path $Source 'CMakeLists.txt'))) {
    Invoke-Checked 'git' @('clone','--depth','1','--branch',$WhisperRef,'https://github.com/ggml-org/whisper.cpp.git',$Source)
}
$Flags = @('-S',$Source,'-B',$Build,'-G','Visual Studio 17 2022','-A','x64',
    '-DCMAKE_CONFIGURATION_TYPES=Release','-DWHISPER_BUILD_SERVER=ON',
    '-DWHISPER_BUILD_TESTS=OFF','-DGGML_NATIVE=OFF','-DBUILD_SHARED_LIBS=ON',
    '-DGGML_CUDA=OFF','-DGGML_VULKAN=OFF','-DGGML_HIP=OFF')
if ($Backend -eq 'Vulkan') {
    if (-not $env:VULKAN_SDK -or -not (Test-Path (Join-Path $env:VULKAN_SDK 'Bin\glslc.exe'))) {
        throw 'Install the LunarG Vulkan SDK (with glslc), then reopen your terminal. An AMD graphics driver alone is not enough to COMPILE the engine.'
    }
    $env:PATH = (Join-Path $env:VULKAN_SDK 'Bin') + ';' + $env:PATH
    # whisper.cpp v1.9.5 requires SPIRV-HeadersConfig.cmake. Install a pinned
    # header-only source package so this does not depend on SDK packaging.
    $SpirvSource = Join-Path $Vendor 'SPIRV-Headers-1.4.328.1'
    $SpirvInstall = Join-Path $Vendor 'spirv-headers-install'
    if (-not (Test-Path (Join-Path $SpirvSource 'CMakeLists.txt'))) {
        Invoke-Checked 'git' @('clone','--depth','1','--branch','vulkan-sdk-1.4.328.1',
            'https://github.com/KhronosGroup/SPIRV-Headers.git',$SpirvSource)
    }
    Invoke-Checked 'cmake' @('-S',$SpirvSource,'-B',(Join-Path $SpirvSource 'build'),
        '-G','Visual Studio 17 2022','-A','x64',"-DCMAKE_INSTALL_PREFIX=$SpirvInstall",'-DSPIRV_HEADERS_ENABLE_TESTS=OFF')
    Invoke-Checked 'cmake' @('--install',(Join-Path $SpirvSource 'build'),'--config','Release')
    $Flags += @('-DGGML_VULKAN=ON',"-DCMAKE_PREFIX_PATH=$SpirvInstall", "-DVulkan_GLSLC_EXECUTABLE=$env:VULKAN_SDK\Bin\glslc.exe")
    if (Test-Path "$env:VULKAN_SDK\Lib\vulkan-1.lib") { $Flags += "-DVulkan_LIBRARY=$env:VULKAN_SDK\Lib\vulkan-1.lib" }
}
if ($Backend -eq 'CUDA') {
    if (-not (Get-Command 'nvcc' -ErrorAction SilentlyContinue)) { throw 'Install the NVIDIA CUDA Toolkit compatible with Visual Studio 2022 and your GPU, then reopen your terminal.' }
    $Flags += '-DGGML_CUDA=ON'
}
Write-Host "`nBuilding whisper.cpp $WhisperRef / $Backend. Vulkan shader compilation can take several minutes.`n" -ForegroundColor Cyan
Invoke-Checked 'cmake' $Flags
Invoke-Checked 'cmake' @('--build',$Build,'--config','Release','--parallel','4','--target','whisper-server')
$Exe = Join-Path $Build 'bin\Release\whisper-server.exe'
if (-not (Test-Path $Exe)) { throw "The build finished, but whisper-server.exe was not found at $Exe" }
# A tiny text locator is consumed by Setup.ps1; no DLLs are moved away from
# the executable because the engine depends on the adjacent backend DLLs.
New-Item -ItemType Directory -Path (Join-Path $Root 'data') -Force | Out-Null
Set-Content -LiteralPath (Join-Path $Root ('data\engine-' + $Backend.ToLowerInvariant() + '.txt')) -Value $Exe -Encoding UTF8
Write-Host "Built: $Exe" -ForegroundColor Green
