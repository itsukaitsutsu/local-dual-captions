# Validation status

This is a source prototype. Windows GPU execution has not been validated here.

## Completed

- 21 Python tests passed: audio segmentation, overlap, text reconciliation, authentication, HTTP/WebSocket behavior, message-size limits, single-session handling, and multipart Whisper request controls.
- 2 JavaScript tests passed: settings sanitization and little-endian PCM16 AudioWorklet output.
- Real Chromium MV3 smoke test passed: extension loading, popup settings, pairing error, Japanese/English shadow-DOM overlay, and stop cleanup. This does not validate real tab-audio capture on Windows.
- PowerShell scripts parsed successfully with PowerShell 7.6.7. Syntax parsing is not a Windows installation/build test.
- whisper.cpp v1.9.5 was compiled and run on Linux CPU with the actual large-v3-turbo-q5_0 model.
- A public Japanese JSUT sample (3.19 seconds) produced: 水をマレーシアから買わなくてはならないのです
- The installed OPUS-MT translator produced: We have to buy water from Malaysia.
- On the constrained two-thread Linux CPU, ASR took about 45.44 seconds and translation about 0.18 seconds. That CPU setup is not fast enough for live captions. These measurements are not an AMD/NVIDIA GPU benchmark.

## Still requires your machine

- Windows prerequisite installation and compiler/SDK compatibility.
- Actual AMD Vulkan or NVIDIA CUDA initialization and real-time throughput.
- End-to-end Chrome tab capture, audio-device behavior, fullscreen behavior, and the websites you use.
- Translation and transcription quality on your actual Japanese media.

Reference audio, not bundled: https://huggingface.co/datasets/japanese-asr/ja_asr.jsut_basic5000/resolve/main/sample.flac

The earlier Argos translator experiment was not selected: a negation example translated incorrectly. The project uses the separate OPUS-MT model instead. The chosen model can still mistranslate; this is not high-stakes interpretation software.
