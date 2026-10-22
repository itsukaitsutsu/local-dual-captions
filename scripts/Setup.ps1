[CmdletBinding()]
param(
    [ValidateSet('Vulkan','CUDA','CPU')][string]$Backend = 'Vulkan',
    [ValidateSet('large-v3-turbo','large-v3-turbo-q8_0','large-v3-turbo-q5_0')][string]$Model = 'large-v3-turbo',
    [string]$ModelPath = '',
    [string]$ServerPath = '',
    [string]$TranslationPath = '',
    [ValidateSet('3.11','3.12','3.13')][string]$PythonVersion = '3.11'
)
$ErrorActionPreference = 'Stop'
$Root = Split-Path $PSScriptRoot -Parent
Push-Location $Root
try {
    if (-not (Get-Command 'py' -ErrorAction SilentlyContinue)) { throw 'Install 64-bit Python 3.11 with the Python launcher first. See START_HERE.html.' }
    $Py = Join-Path $Root '.venv\Scripts\python.exe'
    if (-not (Test-Path $Py)) {
        & py "-$PythonVersion" -m venv (Join-Path $Root '.venv')
        if ($LASTEXITCODE -ne 0) { throw "Could not create the Python $PythonVersion environment. Install that 64-bit Python version first." }
    }
    & $Py -m pip install --disable-pip-version-check -r (Join-Path $Root 'requirements.txt')
    if ($LASTEXITCODE -ne 0) { throw 'Python dependency installation failed. Check internet access and use 64-bit Python 3.11/3.12/3.13.' }
    if ($ServerPath) {
        $ServerPath = (Resolve-Path -LiteralPath $ServerPath).Path
    } else {
        & (Join-Path $PSScriptRoot 'Build-Whisper.ps1') -Backend $Backend
        $ServerPath = (Get-Content -LiteralPath (Join-Path $Root ('data\engine-' + $Backend.ToLowerInvariant() + '.txt')) -Raw).Trim()
    }
    $Arguments = @('-m','bridge.prepare','--backend',$Backend.ToLowerInvariant(),'--server-path',$ServerPath,'--model',$Model)
    if ($ModelPath) { $Arguments += @('--model-path',(Resolve-Path -LiteralPath $ModelPath).Path) }
    if ($TranslationPath) { $Arguments += @('--translation-path',(Resolve-Path -LiteralPath $TranslationPath).Path) }
    & $Py @Arguments
    if ($LASTEXITCODE -ne 0) { throw 'Model preparation failed. Completed downloads are kept, and incomplete downloads can resume.' }
    Write-Host 'Ready. Run Start.cmd, then load the extension folder in Chrome.' -ForegroundColor Green
} finally { Pop-Location }
