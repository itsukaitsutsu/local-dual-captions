<#
.SYNOPSIS
    Download an official, prebuilt whisper-server.exe from the ggml-org
    whisper.cpp release page. No compiler, no SDK, no winget.

.DESCRIPTION
    whisper.cpp publishes ready-to-run Windows builds. This script downloads
    one, verifies its SHA-256, unpacks it into vendor\, and returns the full
    path of whisper-server.exe. All DLLs stay next to the executable, which
    is required: whisper-server loads its ggml backends from that folder.

    -Flavor CpuBlas : whisper-blas-bin-x64.zip        (CPU + OpenBLAS, 21 MB)
    -Flavor Cpu     : whisper-bin-x64.zip             (plain CPU, 9 MB)
    -Flavor Cuda12  : whisper-bin-win-cuda-12.4.0-x64.zip (NVIDIA, 653 MB)
    -Flavor Cuda11  : whisper-bin-win-cuda-11.8.0-x64.zip (NVIDIA, 272 MB)

    AMD / Intel users: whisper.cpp does NOT publish a Vulkan Windows build.
    -AddVulkanDll downloads the official ggml-vulkan.dll from the ggml-org
    llama.cpp release (same upstream project, same ggml backends) and drops it
    next to whisper-server.exe. whisper-server calls ggml_backend_load_all()
    at startup, so it picks the Vulkan backend up at runtime. If the DLL does
    not load, the engine simply stays on CPU - nothing is broken.

.EXAMPLE
    .\scripts\Get-WhisperEngine.ps1 -Flavor CpuBlas -AddVulkanDll
#>
[CmdletBinding()]
param(
    [ValidateSet('CpuBlas', 'Cpu', 'Cuda12', 'Cuda11')][string]$Flavor = 'CpuBlas',
    [switch]$AddVulkanDll,
    [string]$Ref = 'b5454',
    [string]$OutDir = ''
)

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot

# Pinned SHA-256 of the exact files published by ggml-org. A mismatch means the
# file changed or was tampered with, so the download is rejected.
$Assets = @{
    Cpu     = @{ File = 'whisper-bin-x64.zip';              Sha = '6ba69e3482d7826214f90a6a9c84ca07782aec1e1d0c6a7c30c994fd5d816ccb' }
    CpuBlas = @{ File = 'whisper-blas-bin-x64.zip';         Sha = 'b1158bd10edf92c9799149a6fc5d3e58da3f495241d6fb3423088130e88ffbf3' }
    Cuda12  = @{ File = 'whisper-bin-win-cuda-12.4.0-x64.zip'; Sha = 'afef0b881c500958921c3f5523b50e59ee2ec9b6f5cbd25b324c51ed308a957a' }
    Cuda11  = @{ File = 'whisper-bin-win-cuda-11.8.0-x64.zip'; Sha = 'e81c86c542be6e3d7b7245392d4e1c52ab6e5c61dbe38721754bc0ab59d4d027' }
}

# Official ggml-org llama.cpp Windows Vulkan build (source of ggml-vulkan.dll).
$LlamaRef = 'b11819'
$LlamaZip = 'llama-b11819-bin-win-vulkan-x64.zip'
$LlamaSha = 'c3b2484d18258425fe3f69d0b6d07dce01501d6e010578dad3e53150a30df557'
$VulkanDllSha = '80383b460f74f0f937662b3494999243b672e28ae800a9fb29c307a29cdcf6fe'

[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

function Get-Remote {
    param([string]$Uri, [string]$Destination, [string]$ExpectedSha, [string]$Label)

    if ((Test-Path -LiteralPath $Destination) -and $ExpectedSha) {
        Write-Host "  Reusing the existing download: $Label" -ForegroundColor DarkGray
    } else {
        Write-Host "  Downloading $Label" -ForegroundColor DarkGray
        Write-Host "  from $Uri" -ForegroundColor DarkGray
        Invoke-WebRequest -Uri $Uri -OutFile $Destination -UseBasicParsing
    }

    if (-not $ExpectedSha) {
        Write-Host "  WARNING: no pinned SHA-256 for $Label; integrity is NOT verified." -ForegroundColor Yellow
        return
    }

    $actual = (Get-FileHash -LiteralPath $Destination -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actual -ne $ExpectedSha.ToLowerInvariant()) {
        Remove-Item -LiteralPath $Destination -Force -ErrorAction SilentlyContinue
        throw @"
SHA-256 mismatch for $Label
  expected: $ExpectedSha
  actual  : $actual
The file was deleted. Nothing was installed. Check your network/proxy and try again.
"@
    }
    Write-Host '  SHA-256 verified.' -ForegroundColor Green
}

$asset = $Assets[$Flavor]
if (-not $asset) { throw "Unknown flavor: $Flavor" }

$vendor = Join-Path $Root 'vendor'
if ($OutDir) { $vendor = $OutDir }
New-Item -ItemType Directory -Path $vendor -Force | Out-Null

$name = [System.IO.Path]::GetFileNameWithoutExtension($asset.File)
$dest = Join-Path $vendor $name
$zip = Join-Path $vendor $asset.File
$url = "https://github.com/ggml-org/whisper.cpp/releases/download/$Ref/$($asset.File)"

Write-Host ''
Write-Host "Prebuilt whisper.cpp engine ($Flavor, release $Ref)" -ForegroundColor Cyan
Get-Remote -Uri $url -Destination $zip -ExpectedSha $asset.Sha -Label $asset.File

$exe = $null
if (Test-Path -LiteralPath $dest) {
    $exe = Get-ChildItem -LiteralPath $dest -Recurse -Filter 'whisper-server.exe' -ErrorAction SilentlyContinue | Select-Object -First 1
}

if (-not $exe) {
    Write-Host '  Unpacking...' -ForegroundColor DarkGray
    Expand-Archive -LiteralPath $zip -DestinationPath $dest -Force
    $exe = Get-ChildItem -LiteralPath $dest -Recurse -Filter 'whisper-server.exe' -ErrorAction SilentlyContinue | Select-Object -First 1
}

if (-not $exe) { throw "whisper-server.exe was not found inside $($asset.File)" }
Write-Host "  Engine: $($exe.FullName)" -ForegroundColor Green

if ($AddVulkanDll) {
    Write-Host ''
    Write-Host 'Adding the official ggml-vulkan.dll (ggml-org llama.cpp build)' -ForegroundColor Cyan
    $llamaZip = Join-Path $vendor $LlamaZip
    $llamaDir = Join-Path $vendor ([System.IO.Path]::GetFileNameWithoutExtension($LlamaZip))
    $llamaUrl = "https://github.com/ggml-org/llama.cpp/releases/download/$LlamaRef/$LlamaZip"

    Get-Remote -Uri $llamaUrl -Destination $llamaZip -ExpectedSha $LlamaSha -Label $LlamaZip
    if (-not (Test-Path -LiteralPath $llamaDir)) {
        Expand-Archive -LiteralPath $llamaZip -DestinationPath $llamaDir -Force
    }

    $dll = Get-ChildItem -LiteralPath $llamaDir -Recurse -Filter 'ggml-vulkan.dll' -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $dll) { throw 'ggml-vulkan.dll was not found inside the llama.cpp archive.' }

    $dllSha = (Get-FileHash -LiteralPath $dll.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($dllSha -ne $VulkanDllSha.ToLowerInvariant()) {
        throw "ggml-vulkan.dll SHA-256 mismatch (expected $VulkanDllSha, got $dllSha). Nothing was copied."
    }

    $target = Join-Path $exe.DirectoryName 'ggml-vulkan.dll'
    Copy-Item -LiteralPath $dll.FullName -Destination $target -Force
    Write-Host "  Copied ggml-vulkan.dll next to whisper-server.exe" -ForegroundColor Green
    Write-Host '  whisper-server loads every ggml-*.dll in its own folder at startup.' -ForegroundColor DarkGray
    Write-Host '  Check logs\whisper-vulkan.log after starting: it must name your GPU.' -ForegroundColor DarkGray
}

# Only the executable path is written to the pipeline.
Write-Output $exe.FullName
