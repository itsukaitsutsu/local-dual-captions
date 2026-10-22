<#
.SYNOPSIS
    Run the local whisper-server and the caption bridge.

.DESCRIPTION
    Works with a project .venv, the py launcher, or a plain system-wide Python.
    Add -NoVenv to ignore .venv, or -PythonPath to point at python.exe.

.EXAMPLE
    .\scripts\Start.ps1
    .\scripts\Start.ps1 -Backend Vulkan -NoVenv
    .\scripts\Start.ps1 -Threads 8
#>
[CmdletBinding()]
param(
    [ValidateSet('Vulkan', 'CUDA', 'CPU')][string]$Backend,
    [int]$Threads = 0,
    [switch]$NoVenv,
    [string]$PythonPath = ''
)

$ErrorActionPreference = 'Stop'
$Here = $PSScriptRoot
. (Join-Path $Here 'Common.ps1')

$Root = Get-LdcRoot
$py = Resolve-LdcPython -PythonPath $PythonPath -NoVenv:$NoVenv

Push-Location $Root
try {
    $arguments = @('-m', 'bridge.launch')
    if ($Backend) { $arguments += @('--backend', $Backend.ToLowerInvariant()) }
    if ($Threads -gt 0) { $arguments += @('--threads', "$Threads") }
    & $py $arguments
    if ($LASTEXITCODE -ne 0) {
        throw 'The local runner stopped with an error. See the message above, or run scripts\Preflight.ps1.'
    }
} finally {
    Pop-Location
}
