# Setup fix — read this first

Everything in this folder is a drop-in replacement for the files with the same
name in `local-dual-captions-main`. Extract it **over** your project folder and
let it overwrite. Nothing else in the project changes.

This is written for: **AMD/Intel GPU (Vulkan), Windows, system-wide Python,
model already downloaded to `D:\autotrim\...\whisper-models\ggml-large-v3-turbo.bin`**.

---

## 1. Why it would not run

`pip install -r requirements.txt` only installs the Python packages. It does
**not** give you a `whisper-server.exe`, it does not create `data\config.json`,
and it does not download the translation model. Four separate things blocked you:

| # | Blocker | What happened |
|---|---|---|
| 1 | **No engine binary** | The project ships source code only. `Start.cmd` needs `whisper-server.exe`; the default setup tried to *compile* it, which needs Visual Studio 2022 + CMake + Git + the LunarG Vulkan SDK (several GB). |
| 2 | **Scripts demanded a `.venv`** | `Setup.cmd`, `Start.cmd` and `Offline-Test.cmd` all hard-coded `.venv\Scripts\python.exe`. With a system-wide Python they die instantly with "Run Setup.cmd first" — even though your packages were installed. |
| 3 | **`py` launcher requirement** | `Setup.ps1` threw "Install 64-bit Python 3.11 with the Python launcher first" unless the Windows `py` launcher existed. |
| 4 | **No model wiring** | Even with a working engine, nothing told the bridge where your `ggml-large-v3-turbo.bin` was. |

Fixed: the scripts now accept a system Python, and the engine comes from an
**official prebuilt ggml-org binary** (SHA-256 verified). No winget, no
Chocolatey, no compiler, no SDK.

### AMD/Intel note (important)

whisper.cpp publishes **no Vulkan build for Windows** — only CPU, CPU+OpenBLAS
and CUDA. So for AMD/Intel there are two routes:

* **Route A (recommended, no compiler):** download the official CPU+OpenBLAS
  build and drop the official `ggml-vulkan.dll` (from the ggml-org **llama.cpp**
  Windows Vulkan build — same upstream project, same ggml backends) next to
  `whisper-server.exe`. `whisper-server` calls `ggml_backend_load_all()` at
  startup and loads every `ggml-*.dll` in its own folder, so it picks Vulkan up
  at runtime. If the DLL does not load, the engine just stays on CPU — nothing
  breaks.
* **Route B (maximum speed):** compile properly with `-Backend Vulkan` (no
  `-Prebuilt`), which needs VS 2022 Build Tools, CMake, Git and the Vulkan SDK.
  `scripts\Preflight.ps1 -Backend Vulkan -EngineOnly` tells you exactly which of
  those is missing and prints the download link.

---

## 2. Your commands

Open **PowerShell** in your project folder (Shift + right-click inside it →
"Open PowerShell window here") and run these three commands.

```powershell
# 1. Setup: Vulkan backend, prebuilt engine + ggml-vulkan.dll, YOUR model, system Python
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\Setup.ps1 `
  -Backend Vulkan -Prebuilt -PrebuiltFlavor CpuBlas -AddVulkanDll -NoVenv `
  -ModelPath "D:\autotrim\workspace-01a11267-3c03-70c7-ba2b-746368a13969\video-trim-studio\work\whisper-models\ggml-large-v3-turbo.bin"
```

What it does, in order:

1. Finds your Python (`.venv` → `py` → `python`) and installs anything missing
   from `requirements.txt`.
2. Downloads `whisper-blas-bin-x64.zip` (21 MB) from ggml-org, verifies its
   SHA-256, unpacks it to `vendor\`, and adds `ggml-vulkan.dll`.
3. Downloads the OPUS-MT Japanese→English model (~147 MB) to `models\ja-en`.
4. Writes `data\config.json`, prints your **pairing key**, and saves it to
   `data\pairing-key.txt`.

```powershell
# 2. Start the runner (keep this window open)
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\Start.ps1 -NoVenv
```

```powershell
# 3. Check that Vulkan really engaged (in a SECOND PowerShell window)
Get-Content .\logs\whisper-vulkan.log -Tail 40
```

Look for a line naming your GPU (for example `Using device: AMD Radeon ...`).
If it reports CPU instead, the Vulkan DLL did not load — see section 5.

Then: `chrome://extensions` → **Developer mode** → **Load unpacked** → choose
the `extension` folder → open a Japanese video → click the extension → paste
the pairing key → **Start**.

> Your model path lives under a workspace folder that may be temporary. Once it
> works, consider copying `ggml-large-v3-turbo.bin` to something stable like
> `C:\LocalDualCaptions\models\` and re-running setup with the new path.

---

## 3. Other combinations

```powershell
# NVIDIA GPU (official CUDA 12.4 build, 653 MB, no compiler)
.\scripts\Setup.ps1 -Backend CUDA -Prebuilt -PrebuiltFlavor Cuda12 -NoVenv

# CPU only (smallest download; large-v3-turbo will be far too slow for live use)
.\scripts\Setup.ps1 -Backend CPU -Prebuilt -PrebuiltFlavor CpuBlas -NoVenv

# Let setup download the model for you (1.5 GB) instead of using your file
.\scripts\Setup.ps1 -Backend Vulkan -Prebuilt -AddVulkanDll -NoVenv

# Smaller/faster quantized model instead of the full one
.\scripts\Setup.ps1 -Backend Vulkan -Prebuilt -AddVulkanDll -NoVenv -Model large-v3-turbo-q5_0

# Compile from source (fastest Vulkan path, needs the full toolchain)
.\scripts\Setup.ps1 -Backend Vulkan -NoVenv

# Use a venv instead of system Python (original behaviour)
.\scripts\Setup.ps1 -Backend Vulkan -Prebuilt -AddVulkanDll
```

Diagnostics, any time:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\Preflight.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\Preflight.ps1 -Backend Vulkan -EngineOnly
```

---

## 4. Files in this patch

| File | Status | Change |
|---|---|---|
| `scripts\Common.ps1` | **new** | Python resolution (`.venv` → `py` → `python`), package check, install helper |
| `scripts\Get-WhisperEngine.ps1` | **new** | Downloads + SHA-256-verifies official prebuilt engines; optional `ggml-vulkan.dll` |
| `scripts\Preflight.ps1` | **new** | Read-only report: Python, packages, engine, model, ports, toolchain + download links |
| `scripts\Offline-Test.ps1` | **new** | Offline test page without a `.venv` |
| `scripts\Setup.ps1` | **replaced** | System Python, `-Prebuilt`, `-AddVulkanDll`, `-PrebuiltFlavor`, `-NoVenv`, `-PythonPath`, validates `-ModelPath` |
| `scripts\Start.ps1` | **replaced** | System Python, `-NoVenv`, `-PythonPath` |
| `Setup.cmd`, `Start.cmd`, `Offline-Test.cmd` | **replaced** | No longer require `.venv`; `Setup.cmd` asks for your model path |
| `bridge\app.py` | **patched** | Session-lock and lost-last-caption fixes (below) |
| `bridge\launch.py` | **patched** | Prints the engine log when the engine fails; `--engine-timeout`; clearer missing-engine help |

### Bugs fixed in the bridge

1. **"Another caption session is active. Stop it first." forever.** A client
   that vanished without a clean disconnect (crashed offscreen document, closed
   laptop, dead tab) held the single-session lock indefinitely and locked you
   out until you restarted the runner. Sessions are now released after 45 s of
   complete silence.
2. **The last phrase never appeared.** `Segmenter.flush()` existed but was never
   called, so a phrase that was still buffered when audio stopped was thrown
   away. It is now flushed when audio goes quiet for 20 s and when a session
   ends on its own.
3. **A dropped socket could kill a session.** Warning delivery failures no
   longer propagate out of the caption worker.
4. **Silent engine failures.** `launch.py` now prints the last lines of
   `logs\whisper-<backend>.log` when the engine exits or fails to load, which
   is what tells you *why* (missing DLL, bad flag, no GPU, out of memory).

---

## 5. If Vulkan does not engage

```powershell
Get-Content .\logs\whisper-vulkan.log -Tail 40
Get-ChildItem .\vendor\whisper-blas-bin-x64\Release\ggml-vulkan.dll
```

* `ggml-vulkan.dll` missing → rerun setup with `-AddVulkanDll`.
* Lines about `ggml_backend_load` / "failed to load" → the DLL is from a
  different ggml generation than the whisper build. Route B (compile with
  `-Backend Vulkan`) is then the reliable fix.
* GPU listed but captions lag badly → try `-Model large-v3-turbo-q5_0`, and
  use **Fast** profile in the popup.

Every download link used by these scripts is the publisher's own
(ggml-org releases, python.org, cmake.org, git-scm.com, LunarG, NVIDIA,
Microsoft). No third-party mirrors, no package manager.
