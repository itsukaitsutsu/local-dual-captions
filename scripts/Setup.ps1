<#
.SYNOPSIS
    One-time setup for Local Dual Captions. No winget required.

.DESCRIPTION
    Three ways to obtain the whisper-server engine:
      1. -Prebuilt        download an official ggml-org build (no compiler)
      2. -AddVulkanDll    prebuilt CPU build + official ggml-vulkan.dll
                          (the AMD/Intel route; no compiler, no SDK)
      3. (default)        compile from source with scripts\Build-Whisper.ps1

    Python can be a project .venv, the py launcher, or a plain system-wide
    Python. Use -NoVenv to ignore an existing .venv, and -PythonPath to point
    straight at python.exe.

.EXAMPLE
    # AMD / Intel GPU, system Python, using a model you already have:
    .\scripts\Setup.ps1 -Backend Vulkan -Prebuilt -PrebuiltFlavor CpuBlas -AddVulkanDll `
        -ModelPath "D:\models\ggml-large-v3-turbo.bin" -NoVenv

.EXAMPLE
    # NVIDIA GPU:
    .\scripts\Setup.ps1 -Backend CUDA -Prebuilt -PrebuiltFlavor Cuda12 -NoVenv

.EXAMPLE
    # Compile the Vulkan engine yourself (needs VS 2022, CMake, Git, Vulkan SDK):
    .\scripts\Setup.ps1 -Backend Vulkan -NoVenv
#>
[CmdletBinding()]
param(
    [ValidateSet('Vulkan', 'CUDA', 'CPU')][string]$Backend = 'Vulkan',
    [ValidateSet('large-v3-turbo', 'large-v3-turbo-q8_0', 'large-v3-turbo-q5_0')][string]$Model = 'large-v3-turbo',
    [string]$ModelPath = '',
    [string]$ServerPath = '',
    [string]$TranslationPath = '',
    [ValidateSet('3.11', '3.12', '3.13')][string]$PythonVersion = '',
    [switch]$Prebuilt,
    [ValidateSet('CpuBlas', 'Cpu', 'Cuda12', 'Cuda11')][string]$PrebuiltFlavor = '',
    [switch]$AddVulkanDll,
    [switch]$NoVenv,
    [string]$PythonPath = '',
    [switch]$SkipDependencies
)

$ErrorActionPreference = 'Stop'
$Here = $PSScriptRoot
. (Join-Path $Here 'Common.ps1')

$Root = Get-LdcRoot
Push-Location $Root
try {
    Write-Host ''
    Write-Host 'LOCAL DUAL CAPTIONS - setup' -ForegroundColor Cyan
    Write-Host ('Backend: {0}' -f $Backend) -ForegroundColor Cyan

    $py = Resolve-LdcPython -PythonPath $PythonPath -PythonVersion $PythonVersion -NoVenv:$NoVenv
    Assert-LdcPython -Python $py | Out-Null

    if ($SkipDependencies) {
        Write-Host 'Skipping the Python package check (-SkipDependencies).' -ForegroundColor Yellow
    } else {
        Install-LdcRequirements -Python $py
    }

    if ($ServerPath) {
        if (-not (Test-Path -LiteralPath $ServerPath -PathType Leaf)) {
            throw "whisper-server executable not found: $ServerPath"
        }
        $ServerPath = (Resolve-Path -LiteralPath $ServerPath).Path
        Write-Host "Using your engine: $ServerPath" -ForegroundColor Green
    } elseif ($Prebuilt -or $AddVulkanDll) {
        $flavor = $PrebuiltFlavor
        if (-not $flavor) {
            if ($Backend -eq 'CUDA') { $flavor = 'Cuda12' } else { $flavor = 'CpuBlas' }
        }
        $getEngine = Join-Path $Here 'Get-WhisperEngine.ps1'
        if ($AddVulkanDll) {
            $ServerPath = & $getEngine -Flavor $flavor -AddVulkanDll
        } else {
            $ServerPath = & $getEngine -Flavor $flavor
        }
        if (-not $ServerPath) { throw 'The prebuilt engine download did not return an executable path.' }
        $ServerPath = ([string]$ServerPath).Trim()
    } else {
        $preflight = Join-Path $Here 'Preflight.ps1'
        if (Test-Path -LiteralPath $preflight) {
            & $preflight -Backend $Backend -EngineOnly
        }
        & (Join-Path $Here 'Build-Whisper.ps1') -Backend $Backend
        $marker = Join-Path $Root ('data\engine-' + $Backend.ToLowerInvariant() + '.txt')
        $ServerPath = (Get-Content -LiteralPath $marker -Raw).Trim()
    }

    $arguments = @('-m', 'bridge.prepare', '--backend', $Backend.ToLowerInvariant(),
                   '--server-path', $ServerPath, '--model', $Model)
    if ($ModelPath) {
        if (-not (Test-Path -LiteralPath $ModelPath -PathType Leaf)) {
            throw "Model file not found: $ModelPath"
        }
        $ModelPath = (Resolve-Path -LiteralPath $ModelPath).Path
        $arguments += @('--model-path', $ModelPath)
        Write-Host "Using your existing model: $ModelPath" -ForegroundColor Green
    }
    if ($TranslationPath) {
        if (-not (Test-Path -LiteralPath $TranslationPath -PathType Container)) {
            throw "Translation folder not found: $TranslationPath"
        }
        $arguments += @('--translation-path', (Resolve-Path -LiteralPath $TranslationPath).Path)
    }

    Write-Host ''
    & $py $arguments
    if ($LASTEXITCODE -ne 0) {
        throw 'Model preparation failed. Completed downloads are kept, and incomplete downloads resume on the next run.'
    }

    Write-Host ''
    Write-Host 'Setup complete.' -ForegroundColor Green
    Write-Host 'Next: run Start.cmd (or scripts\Start.ps1), then load the extension\ folder at chrome://extensions.' -ForegroundColor Green
    if ($AddVulkanDll) {
        Write-Host ''
        Write-Host 'Vulkan note: after starting, open logs\whisper-vulkan.log and confirm it names your GPU.' -ForegroundColor Yellow
        Write-Host 'If it says CPU only, the ggml-vulkan.dll did not load and the engine is running slowly on CPU.' -ForegroundColor Yellow
    }
} finally {
    Pop-Location
}
