# Local-first security notes

This is a source prototype, not a security-audited product.

## Boundaries

- Runtime services bind to 127.0.0.1. Do not change them to 0.0.0.0, open firewall ports, or reverse-proxy them onto your LAN/internet.
- Extension host permission and CSP allow inference connections only to 127.0.0.1. There is no cloud inference fallback or telemetry.
- The bridge checks HTTP Host, limits WebSocket audio message sizes, requires a Chrome-extension origin, checks the pairing key in constant time, and allows one active session. You can further restrict extension IDs in `data/config.json` (`allowed_extension_ids`).
- WebSocket authentication is a first-message handshake with a five-second deadline, not a key in a URL/query string. The key is never sent to the webpage overlay.
- The upstream whisper.cpp example server has permissive CORS and a model-loading endpoint. The launcher adds a distinct, random, secret `--request-path` prefix to every upstream route; the extension does not receive this secret. Merely binding the upstream server to loopback without this prefix is not the same protection.
- No ffmpeg conversion shell is invoked by the runtime. Audio is a bounded, in-memory WAV containing known PCM16 mono data.
- Model downloads use HTTPS, immutable translator revision/checksums, and fixed SHA-256 speech-model hashes. A caller-supplied model/engine/folder is trusted as the user's explicit local choice, not independently authenticated.
- Caption text is assigned using DOM `textContent`, not evaluated HTML. Overlay CSS is isolated in a shadow root.

## Retained data

- Raw audio and bounded pending audio chunks are in RAM only.
- Rolling transcripts and the translator's 64-entry cache remain in process memory until cleared/exit; cache entries can outlive stopping an individual caption session while the runner stays open.
- The last displayed caption and capture status use Chrome memory-backed `storage.session`. Captions are cleared on stop or browser shutdown; restarting capture does not automatically resume recording.
- Pairing key, port, and appearance settings use `storage.local`, not sync, with access limited to trusted extension contexts. The key and internal engine secret are also in local config files.
- `logs/whisper-*.log` stores third-party engine diagnostics. Upstream code may emit recognized text. Treat these logs as sensitive, and delete them if needed.
- This code has no transcript-export feature, persistent conversation history, microphone capture, or arbitrary website-content collection.

## Threats not solved

An installed malicious extension/app, local malware, another user who can read your files, a compromised upstream dependency, or a compromised OS can bypass local app protections. Loopback data is not encrypted. “Offline” is not synonymous with a hardened sandbox.

Use the tool only for audio you are permitted to process. Follow meeting-recording rules, privacy law, and website terms. Do not rely on machine captions for high-stakes interpretation.

## Uninstall / rotate key

1. Stop capture and stop the runner with Ctrl+C.
2. Remove the unpacked extension at chrome://extensions.
3. Delete the project folder (including `data`, `logs`, `.venv`, `models`, and `vendor`) if no longer needed. Externally supplied model/executable paths are not deleted by the project.
4. To rotate keys instead, remove `data/config.json` and `data/pairing-key.txt`, rerun setup, and pair the extension again. Existing verified model downloads are retained.
