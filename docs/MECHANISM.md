# How it works

## Chrome's built-in feature vs this extension

Google distinguishes **Live Caption**, local speech recognition after its language packs are downloaded, from **Live Translate**, which can send captions to Google. If only translation stalls on a poor connection, the caption recognizer is not necessarily the network-dependent part. This project replaces both stages with local software, but cannot deliver media audio that a streaming site has not downloaded.

It does **not** modify Chrome's built-in accessibility model or read the native caption bubble. It creates its own audio-capture pipeline and webpage overlay using public extension APIs. Chrome's Web Speech API is not used.

## 1. User-authorized tab capture

The user invokes the extension on a media page and clicks Start. The Manifest V3 service worker obtains a tab stream ID with `chrome.tabCapture.getMediaStreamId()` and passes it to an offscreen extension document. That document consumes it with `getUserMedia()`.

An offscreen document is necessary because a toolbar popup closes as soon as you click away, and a service worker has no DOM/Web Audio environment. Capture continues after the popup closes. The source is the selected tab's output—not the microphone, all tabs, or system-wide sound.

Capturing a tab suppresses its usual audio output. A native-rate Web Audio graph reconnects the stream to speakers. A separate **16 kHz** graph lets Chrome resample the captured audio for recognition without reducing the original playback's quality. An AudioWorklet downmixes to mono, converts floating-point samples to little-endian signed PCM16, and sends 100 ms packets to the local bridge over a WebSocket.

## 2. Local transport and speech segmentation

The bridge runs at `127.0.0.1:8765`; this address means **the same computer**, not an internet server. The WebSocket requires an extension origin and a private pairing key. Audio travels only through the computer's loopback interface.

WebRTC VAD evaluates 20 ms frames locally. A 300 ms pre-roll preserves word beginnings. Speech starts after a short positive-vote threshold. A pause of 440–840 ms ends a phrase, depending on profile; continuous speech is split at 3.2, 5.5, or 8.5 seconds.

Forced splits retain 400–800 ms of shared audio. Context is useful when a word crosses a boundary, but creates possible repeated text. The bridge removes exact normalized suffix-prefix matches **only where audio actually overlaps**. It deliberately avoids aggressive fuzzy deletion, which can erase genuinely repeated words. Some boundary duplicates or missed words are still possible.

These are chunked, near-live captions. This implementation does not run a token-streaming speech model and does not implement the research-grade LocalAgreement algorithm. Early drafts can change as phrase context grows; stable word-by-word captions are not promised.

## 3. Whisper's model mechanism

Whisper is an encoder–decoder Transformer. The audio is converted into a log-Mel spectrogram: a time-frequency representation using a perceptual frequency scale. The large-v3 family uses 128 Mel bins. The encoder produces learned audio representations; an autoregressive text decoder predicts tokens conditioned on that representation, language/task markers, and text context.

`ggml-large-v3-turbo.bin` contains model weights in whisper.cpp's GGML-compatible binary format. GGML is not a Chrome API and is not itself the translation algorithm. Quantized Q8/Q5 variants store weights with fewer bits; they reduce disk/weight memory but can change recognition quality. Runtime allocations add to the weight size.

Turbo has a substantially reduced decoder compared with large-v3 and is optimized for transcription. OpenAI explicitly notes that Turbo is **not trained for the speech-translation task**. Therefore this project always sends `language=ja` and `translate=false`. It asks Whisper for Japanese text and never treats its English-only speech-translation flag as a general translation engine.

The bridge sends in-memory WAV data and multipart controls to whisper.cpp's `/inference` endpoint. The WAV is a transport wrapper around the PCM, not a saved audio file. The local model stays loaded between jobs. Runtime controls use greedy decoding with temperature fallback disabled, prioritizing speed and predictable latency; this can trade off recognition quality.

## 4. GPU choices

- **Vulkan:** cross-vendor GPU backend, suitable for supported AMD GPUs and potentially Intel/NVIDIA. Requires a working driver; source compilation additionally needs the Vulkan SDK/shader tools.
- **CUDA:** NVIDIA-specific GPU backend; requires compatible NVIDIA drivers/toolchain.
- **CPU:** fallback, using the compiled x86 backend. Large-v3-turbo can be much too slow for live operation on a weak CPU.

The setup script creates **separate engine builds**. The start script chooses the corresponding executable. It cannot enable CUDA on AMD or make an unsupported GPU work. The extension displays the requested backend, not a measured proof of GPU execution. Read the upstream initialization log to check device selection.

There is also a browser WebAssembly port of whisper.cpp. A browser-only extension is possible in principle, but GGML does not load directly into ordinary JavaScript, and the large model has substantial memory and compute requirements. A native local engine is the more practical prototype for existing Vulkan/CUDA users. This project does not bundle a WASM/GPU inference runtime into Chrome.

## 5. English translation and limited context

The separate text translator uses **Helsinki-NLP OPUS-MT Japanese→English**, loaded in **CTranslate2 INT8 on CPU**. The downloaded files are a community CTranslate2 conversion of that model, pinned to an immutable repository revision and SHA-256 hashes. See `bridge/translation-manifest.json` and `THIRD_PARTY.md` for provenance.

A source SentencePiece model tokenizes Japanese, with Marian's end-of-sequence token. A text encoder–decoder model generates English tokens using beam search. A separate target SentencePiece model decodes them. All files are present locally before runtime; Transformers/PyTorch or a cloud translation service are not required.

Within uninterrupted speech, the bridge keeps a rolling Japanese phrase of at most 320 characters. It appends newly recognized text after overlap reconciliation and retranslates the accumulated phrase. This gives more context than independent word substitution, and keeps the displayed Japanese/English aligned. Explicit Japanese/English sentence punctuation splits independent MT inputs; therefore the translator is **not document-aware**, even when several sentences are displayed.

Japanese appears immediately after ASR. The English line initially says “Translating locally…” and is replaced with the result. The current phrase can be revised as more audio arrives. Translation may still miss implied subjects, humor, names, negation, or idioms. No model can guarantee the intended meaning from incomplete/noisy speech.

## 6. Why delay cannot be zero

Approximate first-word-to-display delay is:

```text
remaining audio-buffer time
+ VAD/pause decision
+ ASR inference
+ queue wait
+ text translation
+ UI update
```

Do not add the full pause gate separately when it is already inside a measured buffered window; the formula identifies contributors, not a precise benchmark equation. Translation may need the end of a Japanese phrase before word order/intent is clear.

Smaller windows produce more frequent requests, but Whisper may still process a padded/large encoder context per request. A 3-second chunk is not necessarily three times cheaper than a 9-second chunk. Reducing audio context could speed this up, but can reduce recognition quality; that optimization is not enabled automatically here.

The extension reports **chunk-tail lag**, measured from the processed chunk's end, not from its first word. RTF compares total job time with new audio duration, excluding the overlapping audio. Sustained RTF < 1 is necessary, though not sufficient, for keeping up. At RTF > 1, backlog grows unless work is dropped or the model/hardware changes. The queue is limited to two pending jobs and reports skipped chunks rather than accumulating unbounded latency.

Seeking a video resets VAD, queued jobs, and phrase context. An in-flight old result is ignored when it returns. Closing/navigating a tab or stopping the local connection stops capture; it does not silently auto-record again.

## Official references

- Chrome captions/translations: https://support.google.com/chrome/answer/10538231?hl=en
- Chrome tab capture: https://developer.chrome.com/docs/extensions/reference/api/tabCapture
- Offscreen capture pattern: https://developer.chrome.com/docs/extensions/how-to/web-platform/screen-capture
- Whisper model limitations: https://github.com/openai/whisper
- whisper.cpp backends: https://github.com/ggml-org/whisper.cpp
- whisper.cpp server: https://github.com/ggml-org/whisper.cpp/tree/v1.9.5/examples/server
- Model files: https://huggingface.co/ggerganov/whisper.cpp
- OPUS-MT original: https://huggingface.co/Helsinki-NLP/opus-mt-ja-en
- CTranslate2: https://opennmt.net/CTranslate2/
