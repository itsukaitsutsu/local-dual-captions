# Serves tools\offline-test.html so you can caption a local media file.
$ErrorActionPreference = 'Stop'
$Here = $PSScriptRoot
. (Join-Path $Here 'Common.ps1')

$Root = Get-LdcRoot
$py = Resolve-LdcPython

Push-Location $Root
try {
    & $py -m bridge.offline_test
    if ($LASTEXITCODE -ne 0) { throw 'The offline test page server stopped with an error.' }
} finally {
    Pop-Location
}
