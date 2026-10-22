[CmdletBinding()]
param(
    [ValidateSet('Vulkan','CUDA','CPU')][string]$Backend,
    [int]$Threads = 0
)
$ErrorActionPreference = 'Stop'
$Root = Split-Path $PSScriptRoot -Parent
$Py = Join-Path $Root '.venv\Scripts\python.exe'
if (-not (Test-Path $Py)) { throw 'Run Setup.cmd or scripts/Setup.ps1 first.' }
Push-Location $Root
try {
    $Arguments = @('-m','bridge.launch')
    if ($Backend) { $Arguments += @('--backend',$Backend.ToLowerInvariant()) }
    if ($Threads -gt 0) { $Arguments += @('--threads',"$Threads") }
    & $Py @Arguments
    if ($LASTEXITCODE -ne 0) { throw 'Local runner stopped with an error. See the message above.' }
} finally { Pop-Location }
