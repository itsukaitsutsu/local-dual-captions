# Shared helpers for the Local Dual Captions scripts.
#
# These helpers work with ANY of these Python setups, in this order:
#   1. A project virtual environment at .venv\Scripts\python.exe
#   2. The Windows "py" launcher
#   3. A normal system-wide Python on PATH (python / python3)
#
# Nothing here uses winget, Chocolatey or Scoop, and nothing needs to be
# installed for these helpers to run.

function Get-LdcRoot {
    return (Split-Path -Parent $PSScriptRoot)
}

function Resolve-LdcPython {
    param(
        [string]$PythonPath = '',
        [switch]$NoVenv,
        [string]$PythonVersion = ''
    )

    $root = Get-LdcRoot

    if ($PythonPath) {
        if (-not (Test-Path -LiteralPath $PythonPath)) {
            throw "Python was not found at: $PythonPath"
        }
        return (Resolve-Path -LiteralPath $PythonPath).Path
    }

    if (-not $NoVenv) {
        $venvExe = Join-Path $root '.venv\Scripts\python.exe'
        if (Test-Path -LiteralPath $venvExe) {
            return (Resolve-Path -LiteralPath $venvExe).Path
        }
    }

    $launcher = Get-Command 'py' -ErrorAction SilentlyContinue
    if ($launcher) {
        $launcherArgs = @()
        if ($PythonVersion) { $launcherArgs += "-$PythonVersion" }
        $launcherArgs += @('-c', 'import sys; print(sys.executable)')
        $found = (& py $launcherArgs 2>$null | Select-Object -Last 1)
        if ($found) {
            $found = ([string]$found).Trim()
            if ($found -and (Test-Path -LiteralPath $found)) { return $found }
        }
    }

    foreach ($name in @('python', 'python3')) {
        $command = Get-Command $name -ErrorAction SilentlyContinue
        if (-not $command) { continue }
        $found = (& $name -c 'import sys; print(sys.executable)' 2>$null | Select-Object -Last 1)
        if ($found) {
            $found = ([string]$found).Trim()
            if ($found -and (Test-Path -LiteralPath $found)) { return $found }
        }
    }

    $message = @'
No Python interpreter was found.

Install Python 3.11 (64-bit) from https://www.python.org/downloads/windows/
and tick "Add python.exe to PATH" while installing. Then open a NEW terminal
and run this script again.

If Python is already installed but not on PATH, point these scripts at it:
  -PythonPath "C:\Users\you\AppData\Local\Programs\Python\Python311\python.exe"
'@
    throw $message
}

function Assert-LdcPython {
    param([string]$Python)

    $info = (& $Python -c 'import sys; print("%d.%d|%d" % (sys.version_info[0], sys.version_info[1], sys.maxsize > 2**32))' 2>$null | Select-Object -Last 1)
    if (-not $info) { throw "The interpreter at $Python did not run." }
    $parts = ([string]$info).Trim().Split('|')
    $version = $parts[0]
    $is64 = $parts[1]

    if ($is64 -ne '1') {
        throw "The Python at $Python is 32-bit. Install 64-bit Python 3.11, 3.12 or 3.13."
    }
    Write-Host ("Python      : {0}  (version {1}, 64-bit)" -f $Python, $version) -ForegroundColor DarkGray
    return $version
}

function Test-LdcRequirements {
    param([string]$Python)

    $probe = 'import importlib.util; mods=["fastapi","starlette","uvicorn","websockets","httpx","ctranslate2","sentencepiece","webrtcvad"]; print(",".join([m for m in mods if importlib.util.find_spec(m) is None]))'
    $missing = (& $Python -c $probe 2>$null | Select-Object -Last 1)
    if (-not $missing) { return $true }
    return ([string]$missing).Trim().Length -eq 0
}

function Install-LdcRequirements {
    param([string]$Python)

    $root = Get-LdcRoot
    $requirements = Join-Path $root 'requirements.txt'

    if (Test-LdcRequirements -Python $Python) {
        Write-Host 'Python packages: already installed (skipping pip).' -ForegroundColor DarkGray
        return
    }

    Write-Host 'Installing Python packages from requirements.txt...' -ForegroundColor Cyan
    & $Python -m pip install --disable-pip-version-check -r $requirements
    if ($LASTEXITCODE -ne 0) {
        Write-Host 'Install into the system Python failed; retrying as a per-user install...' -ForegroundColor Yellow
        & $Python -m pip install --disable-pip-version-check --user -r $requirements
        if ($LASTEXITCODE -ne 0) {
            throw 'Python dependency installation failed. Check your internet connection and that you are using 64-bit Python 3.11, 3.12 or 3.13.'
        }
    }
}

function Get-LdcFileSha256 {
    param([string]$Path)
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

function Write-LdcSection {
    param([string]$Text)
    Write-Host ''
    Write-Host $Text -ForegroundColor Cyan
    Write-Host ('-' * $Text.Length) -ForegroundColor DarkGray
}
