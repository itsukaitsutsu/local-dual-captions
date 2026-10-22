# Local Dual Captions — Japanese + English

A **source prototype** for Windows 10/11 x64 and desktop Chrome 116+. It captions the audio playing in one Chrome tab using local **whisper.cpp + `ggml-large-v3-turbo.bin`**, then translates Japanese text to English with a separate local **OPUS-MT** model. Both lines appear in a draggable webpage overlay.

**Start with `START_HERE.html`.** It is a self-contained, offline-readable setup guide and caption-appearance demo. The demo is not live model inference.

## What is included

- Manifest V3 Chrome extension: tab capture, persistent offscreen audio worker, dual caption overlay, pairing key, style settings, and Fast/Balanced/More-context profiles.
- Local Python bridge with WebRTC VAD, bounded audio windows, overlap deduplication, short rolling-utterance context, and an explicit overload warning.
- Windows setup/build/start scripts with **Vulkan (AMD/Intel/supported NVIDIA)**, **CUDA (NVIDIA)**, and **CPU** choices.
- Full, Q8, and Q5 variants of the requested Turbo model. Model downloads resume after interruptions and are SHA-256 checked.
- An offline media test page, tests, architecture/security notes, and a candid validation report.

**Not included:** compiled Windows binaries, AI model weights, a signed Chrome Web Store package, or a guarantee of real-time speed or translation accuracy. These sources must be installed and tested on your machine. GPU support depends on drivers, hardware, SDK versions, and the upstream engine.

## Architecture

```text
Chrome tab audio
  ├─ native-rate AudioContext → speakers (original playback preserved)
  └─ 16 kHz mono AudioContext → AudioWorklet → PCM16 over local WebSocket
       → Python bridge / WebRTC VAD / bounded overlapping windows
       → local whisper-server / large-v3-turbo / language=ja / translate=false
       → Japanese transcript, immediately displayed
       → local CTranslate2 INT8 / OPUS-MT ja→en / CPU
       → Japanese + English overlay, translation revised as the phrase grows
```

Turbo is a transcription model, **not the translation stage**. Setting Whisper's `translate` flag does not turn Turbo into a reliable translator. Our separate Japanese→English model avoids that mistake.

## 1. Windows prerequisites

For every installation:

- Windows 10/11 **x64**; an AVX2-capable CPU; current desktop Chrome.
- **Python 3.11 x64**, including the `py` launcher. Python 3.12/3.13 can be selected with `-PythonVersion`; 3.11 is the recommended Windows choice.
- Microsoft Visual C++ 2015–2022 x64 Redistributable for native Python/engine dependencies.
- Sufficient disk space for models, Python packages, and build tools. 16 GB system RAM is a reasonable starting point, not a measured minimum; runtime GPU memory use exceeds model-file size.

If compiling the engine (the default setup route):

- Git for Windows; CMake 3.22+ in PATH.
- **Visual Studio 2022 Build Tools**, workload **Desktop development with C++**, MSVC x64 tools, and a Windows SDK.
- **Vulkan route:** current graphics driver with Vulkan compute support and the **LunarG Vulkan SDK**, including `glslc`. The script also installs a pinned, header-only SPIRV-Headers source dependency. The graphics driver by itself is not a compiler SDK.
- **CUDA route:** NVIDIA driver and an NVIDIA CUDA Toolkit compatible with the GPU and Visual Studio 2022; `nvcc` must be in PATH. Install the C++ tools before the CUDA Toolkit/VS integration.
- **CPU route:** no GPU SDK required.

Install tools from their publishers, then open a new terminal. Build tools/SDKs can be several GB. **If you already have a compatible `whisper-server.exe`, reuse it and skip compilation** (next section). Do not install arbitrary prebuilt GPU binaries from unknown publishers.

## 2. One-time setup

Extract the entire project to a stable folder such as `C:\LocalDualCaptions`. Do not run scripts inside the ZIP.

### Interactive route

Double-click **`Setup.cmd`** and choose Vulkan, CUDA, or CPU, then choose the model variant. The default is the full requested `large-v3-turbo` model.

### Command-line route (PowerShell, from the project folder)

AMD / Vulkan:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\Setup.ps1 -Backend Vulkan
```

NVIDIA / CUDA:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\Setup.ps1 -Backend CUDA
```

CPU:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\Setup.ps1 -Backend CPU
```

Smaller download / lower weight memory, with a possible accuracy trade-off:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\Setup.ps1 -Backend Vulkan -Model large-v3-turbo-q5_0
```

Reuse your existing Vulkan server and model (no source compilation):

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\Setup.ps1 -Backend Vulkan -ServerPath "C:\whisper\whisper-server.exe" -ModelPath "C:\Models\ggml-large-v3-turbo.bin"
```

Keep the executable's required DLLs beside it. Use **`whisper-server.exe`**, not `whisper-cli.exe`; the server must support `/health`, `/inference`, `--request-path`, and `verbose_json` (the pinned implementation is whisper.cpp v1.9.5). The backend flag describes the executable you supplied; it cannot add Vulkan or CUDA to a CPU-only binary.

You may supply a predownloaded OPUS-MT **CTranslate2 folder** with `-TranslationPath "C:\Models\opus-ja-en"`. It must contain `model.bin`, `config.json`, `shared_vocabulary.json`, `source.spm`, and `target.spm`. The known-good repository/revision/checksums are in `bridge/translation-manifest.json`. No `.pt`, `.safetensors`, or GGUF translation file is accepted by this implementation.

The `ExecutionPolicy Bypass` above applies to that launched PowerShell process only; it is not a permanent system policy change. Inspect scripts before running them. Administrator privileges are not required by the runner.

### Downloads

| Speech model | Download size | Notes |
|---|---:|---|
| `ggml-large-v3-turbo.bin` | 1.51 GiB | Default; full precision weights |
| `ggml-large-v3-turbo-q8_0.bin` | 834 MiB | Quantized alternative |
| `ggml-large-v3-turbo-q5_0.bin` | 547 MiB | Smaller download; accuracy can differ |
| OPUS-MT Japanese→English files | about 147 MiB total | Separate translator; runs INT8 on CPU |

Python packages, compiler tools, and source downloads are additional. File size is **not** runtime RAM/VRAM use. A completed download is verified and reused. An interrupted `.part` download is retained and resumed when setup runs again. If a checksum fails, remove the indicated corrupt file before retrying.

## 3. Start the local engine

Double-click **`Start.cmd`** and keep the terminal open. Wait until the bridge has started; the first model load can take time.

The terminal prints a **private pairing key**. It is also in `data\pairing-key.txt`. Do not share this file or `data\config.json`.

To switch to another backend you have already installed:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\Start.ps1 -Backend CUDA
```

Run setup once per backend to create its separate build. GPU selection cannot be changed by a caption-style dropdown. The extension shows the **requested** backend; check `logs\whisper-<backend>.log` to confirm the GPU actually initialized. A backend may fall back to CPU.

## 4. Install the Chrome extension

1. Open **`chrome://extensions`** in desktop Chrome.
2. Enable **Developer mode**.
3. Click **Load unpacked** and select this project's **`extension` folder**, not the project root or ZIP.
4. Pin the extension if desired. Open it and paste the pairing key.
5. Click **Check connection**. The local runner should report ready.
6. Open an ordinary HTTP/HTTPS page with Japanese audio, start playback, open the extension, and click **Caption this tab**.
7. Japanese appears first; its English translation follows. The translation can be revised as more of the same utterance arrives. Drag the caption header to move it.
8. Click **Stop captions**, the overlay's × button, or close the captured tab to stop capture. Press **Ctrl+C** in the runner terminal to stop both local server processes.

No microphone permission is requested. Other tabs and desktop applications are not captured. Switching tabs does not switch the captured source. Page navigation stops capture, and you must start it again. Chrome settings, Web Store/PDF viewer pages, direct `file://` pages, DRM-protected audio, and some players may not support this overlay/capture path. Container fullscreen is supported; native video/iframe fullscreen can hide the overlay—use theatre mode.

## 5. Verify it really works offline

1. Finish setup while connected and start `Start.cmd`.
2. Run **`Offline-Test.cmd`**, which serves the bundled test player at `http://127.0.0.1:8090/offline-test.html`.
3. Open that address **in Chrome**, choose your own downloaded Japanese audio/video file, and press play.
4. Start captions from the extension. Now disconnect Wi-Fi/Ethernet and verify both Japanese and English continue.
5. Stop the test player server with Ctrl+C in its terminal when done.

The selected media file stays in the browser; it is not uploaded. A streaming site's audio cannot keep arriving when the site itself is buffering. Offline inference does not fix that separate network bottleneck.

## Profiles and latency

| Profile | Continuous-speech window cap | Pause gate | Shared boundary audio |
|---|---:|---:|---:|
| Fast | 3.2 s | 440 ms | 400 ms |
| Balanced | 5.5 s | 640 ms | 600 ms |
| More context | 8.5 s | 840 ms | 800 ms |

Speech pauses can finish a chunk earlier. These are **buffer settings, not promised end-to-end latency**. Add ASR time, translation time, and any pending work. Shorter windows are not always faster in practice: Whisper can still do a large amount of fixed encoder work per invocation. A good GPU helps; Turbo on a weak CPU may not keep up at all.

The popup's **chunk-tail lag** estimates time since the end of a processed audio chunk, not time since its first spoken word. **RTF** is processing time divided by the chunk's new audio duration; sustained RTF above 1 means the system is slower than incoming audio. There is one in-flight job and at most two queued jobs. On overload, older pending chunks are explicitly skipped to stay near the present; that loses words, rather than secretly growing an unlimited delay.

Japanese often puts key information near the end of a phrase. More context can help translation, but no setting guarantees accurate meanings, names, negation, sarcasm, idioms, or overlapping speakers. The translator is a compact sentence-level MT model, not a document-aware LLM. This is not suitable for medical, legal, or other high-stakes interpretation.

## Privacy and security

- Both runtime servers bind to **127.0.0.1**, not your LAN. Never expose them publicly.
- Extension requests have a random pairing key; WebSocket clients must have a Chrome-extension origin and authenticate before sending audio. The internal Whisper server uses a separate random, secret request-path prefix because its upstream example server has permissive CORS and a model-load endpoint.
- The bridge uses no cloud APIs, telemetry, Web Speech recognition, or runtime model download. Setup needs internet; ordinary website playback may need internet.
- Audio chunks and rolling text stay in memory. The last displayed caption also lives in Chrome's memory-backed `storage.session`, cleared at stop/browser shutdown. Pairing/settings are saved locally, not Chrome sync. The translator has a bounded in-memory text cache.
- Engine diagnostic logs are saved under `logs`. Third-party engine behavior may include recognition text in logs; treat them as sensitive and delete them when appropriate.
- Audio is not encrypted on loopback. This is protection against accidental web/LAN access, not against malicious software or another user with access to your files/computer. Use captions with other people's audio only where you have permission.

## Troubleshooting

| Symptom | What to check |
|---|---|
| Cannot reach runner | Keep Start.cmd open; wait for startup; check port 8765 and the pairing key. If you changed ports in config, update the extension too. Check local firewall/Chrome network permissions; do not disable browser security flags. |
| DLL load error | Install the x64 VC++ Redistributable; use x64 Python; keep engine/backend DLLs with the executable. |
| Vulkan not found while compiling | Install the full LunarG SDK with `glslc`; reopen the terminal; check `VULKAN_SDK`. SPIRV-Headers is built by the script. |
| CUDA build fails | Check NVIDIA driver, Toolkit/GPU compatibility, `nvcc`, and Visual Studio 2022 C++/CUDA integration. |
| No GPU acceleration | Read the engine log. A Vulkan/CUDA UI label alone does not prove the device was selected. Try a supported driver or CPU fallback. |
| Captions lag or skip | Inspect RTF; close other GPU workloads; try Q5/Q8 and different profiles; confirm GPU initialization. If necessary use a smaller Whisper model via `-ModelPath` (outside the default Turbo configuration). |
| Audio goes quiet | Stop/restart capture. The extension intentionally restores playback with a native-rate AudioContext. Some device/OS capture policies may still interfere. |
| Background music becomes words | Try Strict VAD, cleaner speech, or a longer profile. VAD reduces but cannot eliminate hallucinations/music confusion. |
| Quiet speech is missing | Try Lenient VAD and check the actual media volume/source. |
| Captions vanish in fullscreen | Exit native video fullscreen or use the player's theatre/container fullscreen mode. |
| Download checksum failure | Delete only the named corrupt file/`.part` and retry setup. Existing valid files are retained. |
| Moved project / changed key | Rerun setup with correct paths; paste the current key again. The runner stores absolute model/executable paths. |

## Developer validation

See `docs/VALIDATION.md` for exactly what was tested and what was not. Windows Vulkan/CUDA execution and your GPU's real-time speed are **not validated in this sandbox**.

```powershell
.\.venv\Scripts\python -m pip install -r requirements-dev.txt
.\.venv\Scripts\python -m pytest -q
node --test tests/extension.test.mjs
.\.venv\Scripts\python -m playwright install chromium
.\.venv\Scripts\python tests/browser_smoke.py
```

More detail: `docs/MECHANISM.md`, `docs/SECURITY.md`, `THIRD_PARTY.md`.
