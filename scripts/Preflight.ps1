<#
.SYNOPSIS
    Report exactly what is present and what is missing. Changes nothing.

.DESCRIPTION
    Run this first when something does not start. It checks Python, the Python
    packages, the whisper-server executable, the model file, the local ports,
    and (with -EngineOnly) the compiler toolchain. Every download link it prints
    is the publisher's own page - no package manager is involved.

.EXAMPLE
    .\scripts\Preflight.ps1
    .\scripts\Preflight.ps1 -Backend Vulkan -EngineOnly
#>
[CmdletBinding()]
param(
    [ValidateSet('Vulkan', 'CUDA', 'CPU')][string]$Backend = '',
    [switch]$EngineOnly,
    [switch]$NoVenv,
    [string]$PythonPath = ''
)

$ErrorActionPreference = 'Stop'
$Here = $PSScriptRoot
. (Join-Path $Here 'Common.ps1')

$Root = Get-LdcRoot
$problems = 0

function Show-Ok { param([string]$Text) Write-Host ("  [ OK ] {0}" -f $Text) -ForegroundColor Green }
function Show-Bad { param([string]$Text) Write-Host ("  [FAIL] {0}" -f $Text) -ForegroundColor Red }
function Show-Info { param([string]$Text) Write-Host ("         {0}" -f $Text) -ForegroundColor DarkGray }

function Test-PortFree {
    param([int]$Port)
    $listener = $null
    try {
        $listener = New-Object System.Net.Sockets.TcpListener([System.Net.IPAddress]::Loopback, $Port)
        $listener.Start()
        return $true
    } catch {
        return $false
    } finally {
        if ($listener) { $listener.Stop() }
    }
}

Write-Host ''
Write-Host 'LOCAL DUAL CAPTIONS - preflight report' -ForegroundColor Cyan
Write-Host ('Project folder: {0}' -f $Root) -ForegroundColor DarkGray

# ---------------------------------------------------------------- Python ----
Write-LdcSection 'Python'
$py = ''
try {
    $py = Resolve-LdcPython -PythonPath $PythonPath -NoVenv:$NoVenv
    Show-Ok "Interpreter: $py"
} catch {
    Show-Bad $_.Exception.Message
    Show-Info 'Download: https://www.python.org/downloads/windows/  (tick "Add python.exe to PATH")'
    $problems++
}

if ($py) {
    try {
        $version = Assert-LdcPython -Python $py
    } catch {
        Show-Bad $_.Exception.Message
        $problems++
    }
    if (Test-LdcRequirements -Python $py) {
        Show-Ok 'Runtime packages from requirements.txt are importable.'
    } else {
        $probe = 'import importlib.util; mods=["fastapi","starlette","uvicorn","websockets","httpx","ctranslate2","sentencepiece","webrtcvad"]; print(",".join([m for m in mods if importlib.util.find_spec(m) is None]))'
        $missing = (& $py -c $probe 2>$null | Select-Object -Last 1)
        Show-Bad "Missing Python packages: $missing"
        Show-Info 'Fix:  .\scripts\Setup.ps1 -NoVenv      (or: pip install -r requirements.txt)'
        $problems++
    }
}

# ----------------------------------------------------------- Configuration --
if (-not $EngineOnly) {
    Write-LdcSection 'Configuration'
    $configPath = Join-Path $Root 'data\config.json'
    if (Test-Path -LiteralPath $configPath) {
        try {
            $config = Get-Content -LiteralPath $configPath -Raw | ConvertFrom-Json
            Show-Ok "data\config.json (backend: $($config.backend))"
            if ($Backend -and ($Backend.ToLowerInvariant() -ne $config.backend)) {
                Show-Info "You asked for $Backend; the config currently uses $($config.backend). Start with -Backend $Backend to switch."
            }
            foreach ($entry in $config.engine_paths.PSObject.Properties) {
                $path = $entry.Value
                if ($path -and (Test-Path -LiteralPath $path -PathType Leaf)) {
                    Show-Ok "engine_paths.$($entry.Name) -> $path"
                } else {
                    Show-Bad "engine_paths.$($entry.Name) -> $path (missing)"
                    $problems++
                }
            }
            if ($config.model_path) {
                if (Test-Path -LiteralPath $config.model_path -PathType Leaf) {
                    $size = [math]::Round((Get-Item -LiteralPath $config.model_path).Length / 1MB, 1)
                    Show-Ok ("model_path -> {0}  ({1} MB)" -f $config.model_path, $size)
                } else {
                    Show-Bad "model_path -> $($config.model_path) (missing)"
                    $problems++
                }
            }
            if ($config.translation_path) {
                if (Test-Path -LiteralPath $config.translation_path -PathType Container) {
                    Show-Ok "translation_path -> $($config.translation_path)"
                } else {
                    Show-Bad "translation_path -> $($config.translation_path) (missing)"
                    $problems++
                }
            }
        } catch {
            Show-Bad "data\config.json could not be read: $($_.Exception.Message)"
            $problems++
        }
    } else {
        Show-Bad 'data\config.json is missing - setup has not completed yet.'
        Show-Info 'Fix:  .\scripts\Setup.ps1 -Backend <Vulkan|CUDA|CPU> -Prebuilt -NoVenv'
        $problems++
    }

    Write-LdcSection 'Local ports'
    foreach ($port in @(8765, 8178)) {
        if (Test-PortFree -Port $port) {
            Show-Ok "Port $port is free."
        } else {
            Show-Bad "Port $port is already in use (an older runner may still be open)."
            $problems++
        }
    }
}

# -------------------------------------------------------- Compiler toolchain
if ($EngineOnly -or $Backend) {
    Write-LdcSection 'Engine toolchain'
    foreach ($tool in @('git', 'cmake')) {
        $command = Get-Command $tool -ErrorAction SilentlyContinue
        if ($command) { Show-Ok "$tool -> $($command.Source)" }
        else {
            Show-Bad "$tool was not found in PATH."
            if ($tool -eq 'git') { Show-Info 'Download: https://git-scm.com/download/win' }
            else { Show-Info 'Download: https://cmake.org/download/  (tick "Add CMake to PATH")' }
            $problems++
        }
    }

    $vswhere = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio\Installer\vswhere.exe'
    if (Test-Path -LiteralPath $vswhere) {
        $vs = & $vswhere -latest -version '[17.0,18.0)' -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
        if ($vs) { Show-Ok "Visual Studio 2022 C++ tools -> $vs" }
        else {
            Show-Bad 'Visual Studio 2022 C++ tools were not found.'
            Show-Info 'Download: https://visualstudio.microsoft.com/downloads/#build-tools-for-visual-studio-2022'
            Show-Info 'Select "Desktop development with C++" in the installer.'
            $problems++
        }
    } else {
        Show-Bad 'Visual Studio Installer / vswhere.exe was not found.'
        Show-Info 'Download: https://visualstudio.microsoft.com/downloads/#build-tools-for-visual-studio-2022'
        $problems++
    }

    if (-not $Backend -or $Backend -eq 'Vulkan') {
        if ($env:VULKAN_SDK -and (Test-Path -LiteralPath (Join-Path $env:VULKAN_SDK 'Bin\glslc.exe'))) {
            Show-Ok "Vulkan SDK -> $env:VULKAN_SDK"
        } else {
            Show-Bad 'LunarG Vulkan SDK (with glslc) was not found.'
            Show-Info 'Download: https://vulkan.lunarg.com/sdk/home#windows  (then open a new terminal)'
            $problems++
        }
    }

    if ($Backend -eq 'CUDA') {
        $nvcc = Get-Command 'nvcc' -ErrorAction SilentlyContinue
        if ($nvcc) { Show-Ok "nvcc -> $($nvcc.Source)" }
        else {
            Show-Bad 'nvcc was not found in PATH.'
            Show-Info 'Download: https://developer.nvidia.com/cuda-toolkit-archive'
            $problems++
        }
    }
}

Write-Host ''
if ($problems -eq 0) {
    Write-Host 'Everything checked looks good.' -ForegroundColor Green
    if (-not $EngineOnly) {
        Write-Host 'Start the runner with:  .\scripts\Start.ps1 -NoVenv' -ForegroundColor Green
    }
} else {
    Write-Host ("{0} problem(s) found. Fix the items above, then run this script again." -f $problems) -ForegroundColor Yellow
}
