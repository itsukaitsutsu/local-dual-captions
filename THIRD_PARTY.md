# Third-party components and model provenance

No AI weights, third-party executable, compiler, or third-party source tree is redistributed in this small source package. Setup downloads the listed artifacts. Review their licenses before redistributing a completed installation.

## Speech recognition

- **OpenAI Whisper**, model/code: https://github.com/openai/whisper — MIT.
- **whisper.cpp**, local inference engine: https://github.com/ggml-org/whisper.cpp — MIT; default setup tag **v1.9.5** (observed commit `d1be6fde11ac6e0407606b4e42fe72d34add8037`). Its vendored dependencies carry their own notices.
- GGML Turbo models: https://huggingface.co/ggerganov/whisper.cpp. `bridge/prepare.py` contains the pinned SHA-256 hashes for the full/Q8/Q5 variants.
- **SPIRV-Headers**, source-only Vulkan build dependency: https://github.com/KhronosGroup/SPIRV-Headers, tag `vulkan-sdk-1.4.328.1`; see its bundled license files. Visual Studio, Vulkan SDK/drivers, CUDA, and Windows remain subject to their publishers' licenses.

## Text translation

- Original model: **Helsinki-NLP/opus-mt-ja-en** — Japanese→English; model card lists **Apache-2.0**. https://huggingface.co/Helsinki-NLP/opus-mt-ja-en
- Downloaded runtime conversion: **gaudi/opus-mt-ja-en-ctranslate2**, a community CTranslate2 conversion, not a new OpenAI model and not a model published by this project. https://huggingface.co/gaudi/opus-mt-ja-en-ctranslate2
- Conversion revision: `599e1e01d8e539db0eb9270e329bc5969803c20e`. All installed files are SHA-256 checked against `bridge/translation-manifest.json`. The community README is retained in the model folder.
- The downloaded weights are float16; CTranslate2 loads/quantizes them for **INT8 CPU** inference. `source.spm` and `target.spm` are the separate SentencePiece models. No pickle/Python model code is loaded from that repository.
- Apache License 2.0: https://www.apache.org/licenses/LICENSE-2.0

## Python / test software

Runtime dependencies in `requirements.txt`: FastAPI (MIT), Starlette (BSD), Uvicorn (BSD), websockets (BSD), HTTPX (BSD), WebRTC VAD wrapper / webrtcvad-wheels (MIT wrapper with WebRTC's BSD notices), CTranslate2 (MIT), SentencePiece (Apache-2.0), plus their transitive dependencies. Consult installed distributions for authoritative notices. Development tools include pytest, Ruff, Playwright/Chromium, and Node's built-in test runner.

## Validation sample, not bundled

A Japanese JSUT sample was retrieved for engineering validation only:
https://huggingface.co/datasets/japanese-asr/ja_asr.jsut_basic5000/resolve/main/sample.flac

The audio file is not included in the deliverable. Dataset/model-card terms apply. A public transcript snippet and the observed recognition/translation outputs are recorded in `docs/VALIDATION.md`; no private user recording was used.
