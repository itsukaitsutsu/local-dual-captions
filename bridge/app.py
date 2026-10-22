from __future__ import annotations

import asyncio
import contextlib
import hmac
import logging
import re
import time
from contextlib import asynccontextmanager
from collections.abc import Callable

from fastapi import FastAPI, Header, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from . import __version__
from .audio import PROFILES, Segmenter
from .config import Config
from .engines import JapaneseTranslator, WhisperEngine
from .text import join_japanese, strip_overlap

log = logging.getLogger("dual-captions")
EXTENSION_ORIGIN = re.compile(r"^chrome-extension://([a-p]{32})$")
# A silent client (closed laptop lid, crashed offscreen document, dead tab)
# used to hold the single session lock forever and block every later session
# with "Another caption session is active". Release it after this much quiet.
IDLE_TIMEOUT_SECONDS = 45.0
# If a source stops producing audio entirely (paused video, muted tab, capture
# ended) the trailing phrase would sit in the buffer forever. Flush it after
# this much silence on the wire. Heartbeat pings do not count as audio.
AUDIO_GAP_SECONDS = 20.0
# Time allowed to finish the trailing utterance when a session ends by itself.
DRAIN_TIMEOUT_SECONDS = 8.0


def create_app(config: Config, *, engine=None, translator=None,
               detector_factory: Callable | None = None) -> FastAPI:
    config.validate()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.engine = engine or WhisperEngine(config.engine_url)
        app.state.translator = translator or await asyncio.to_thread(
            JapaneseTranslator, config.translation_path, config.translation_threads)
        # Warm once, with bundled sample text only. No network is used by MT.
        await asyncio.to_thread(app.state.translator.translate, "こんにちは。")
        app.state.session_lock = asyncio.Lock()
        app.state.inference_lock = asyncio.Lock()
        yield
        await app.state.engine.close()

    app = FastAPI(title="Local Dual Captions", version=__version__, lifespan=lifespan,
                  docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "testserver"])
    app.add_middleware(
        CORSMiddleware, allow_origin_regex=r"chrome-extension://[a-p]{32}",
        allow_methods=["GET"], allow_headers=["X-Caption-Key"],
    )

    @app.get("/health")
    async def health():
        return {"service": "Local Dual Captions", "version": __version__}

    @app.get("/status")
    async def status(x_caption_key: str = Header(default="")):
        if not x_caption_key.isascii() or not hmac.compare_digest(x_caption_key, config.token):
            raise HTTPException(401, "Pairing key is missing or incorrect.")
        ready = await app.state.engine.ready()
        return {
            "ready": ready, "backend": config.backend,
            "recognition": "Whisper large-v3-turbo (Japanese)",
            "translation": "OPUS-MT JA → EN / CTranslate2 INT8 CPU",
            "busy": app.state.session_lock.locked(), "version": __version__,
        }

    @app.websocket("/live")
    async def live(ws: WebSocket):
        match = EXTENSION_ORIGIN.fullmatch(ws.headers.get("origin", ""))
        if not match or (config.allowed_extension_ids and match[1] not in config.allowed_extension_ids):
            await ws.close(code=1008, reason="Chrome extension origin required")
            return
        await ws.accept()
        try:
            hello = await asyncio.wait_for(ws.receive_json(), timeout=5)
        except (TimeoutError, ValueError, WebSocketDisconnect):
            await ws.close(code=1008, reason="Pairing handshake required")
            return
        if (not isinstance(hello, dict) or hello.get("type") != "hello"
                or not isinstance(hello.get("token"), str)
                or not hello["token"].isascii()
                or not hmac.compare_digest(hello["token"], config.token)):
            await ws.close(code=1008, reason="Incorrect pairing key")
            return
        profile = hello.get("profile", "balanced")
        mode = hello.get("vadMode", 2)
        if profile not in PROFILES or mode not in (0, 1, 2, 3):
            await ws.close(code=1008, reason="Invalid profile or VAD mode")
            return
        if app.state.session_lock.locked():
            await ws.send_json({"type": "error", "message": "Another caption session is active. Stop it first."})
            await ws.close(code=1013)
            return
        if not await app.state.engine.ready():
            await ws.send_json({"type": "error", "message": "Whisper engine is not ready. Check the runner terminal."})
            await ws.close(code=1013)
            return

        async with app.state.session_lock:
            detector = detector_factory() if detector_factory else None
            segmenter = Segmenter(profile=profile, vad_mode=mode, detector=detector)
            pending: asyncio.Queue = asyncio.Queue(maxsize=2)
            send_lock = asyncio.Lock()
            dropped = 0
            caption_id = 0

            busy = False

            async def send(payload):
                async with send_lock:
                    await ws.send_json(payload)

            async def warn(payload):
                # Warnings must never kill the session, even on a dead socket.
                try:
                    await send(payload)
                except Exception:  # noqa: BLE001 - connection already gone
                    log.debug("Could not deliver a warning to the extension")

            async def enqueue(chunk):
                nonlocal dropped
                if pending.full():
                    pending.get_nowait()
                    pending.task_done()
                    dropped += 1
                    await warn({"type": "warning", "code": "overload", "dropped": dropped,
                                "message": "Engine is behind. An unprocessed audio chunk was skipped to stay live. Try Fast mode or a smaller/quantized model."})
                pending.put_nowait(chunk)

            async def worker():
                nonlocal caption_id, busy
                last_raw = ""
                last_end = -1.0
                last_utterance = -1
                last_generation = -1
                rolling = ""
                while True:
                    chunk = await pending.get()
                    busy = True
                    try:
                        if chunk.generation != segmenter.generation:
                            continue
                        if chunk.generation != last_generation:
                            last_raw, rolling, last_end, last_utterance = "", "", -1.0, -1
                            last_generation = chunk.generation
                        began = time.monotonic()
                        async with app.state.inference_lock:
                            recognition = await app.state.engine.transcribe(chunk, prompt=rolling)
                            asr_ms = (time.monotonic() - began) * 1000
                            if chunk.generation != segmenter.generation:
                                continue
                            raw = recognition.text
                            overlaps = (chunk.overlap_s > 0 and chunk.start_s < last_end
                                        and chunk.utterance_id == last_utterance)
                            addition = strip_overlap(last_raw, raw, has_audio_overlap=overlaps)
                            if chunk.utterance_id != last_utterance:
                                rolling = ""
                            last_raw, last_end, last_utterance = raw, chunk.end_s, chunk.utterance_id
                            if not addition:
                                continue
                            rolling = join_japanese(rolling, addition)
                            caption_id += 1
                            current_id = caption_id
                            await send({"type": "caption", "id": current_id, "ja": rolling, "en": "",
                                        "translating": True, "final": chunk.final,
                                        "asrMs": round(asr_ms), "queue": pending.qsize()})
                            mt_begin = time.monotonic()
                            english = await asyncio.to_thread(app.state.translator.translate, rolling)
                            mt_ms = (time.monotonic() - mt_begin) * 1000
                        if chunk.generation != segmenter.generation:
                            continue
                        total_ms = (time.monotonic() - began) * 1000
                        lag_ms = max(0, (time.monotonic() - chunk.stream_started - chunk.end_s) * 1000)
                        await send({"type": "caption", "id": current_id, "ja": rolling, "en": english,
                                    "translating": False, "final": chunk.final,
                                    "asrMs": round(asr_ms), "mtMs": round(mt_ms),
                                    "lagMs": round(lag_ms), "rtf": round(total_ms / (chunk.new_duration * 1000), 2),
                                    "queue": pending.qsize(), "dropped": dropped})
                    except asyncio.CancelledError:
                        raise
                    except Exception as exc:
                        # Never log user transcript or the request/pairing secret.
                        log.warning("Caption job failed (%s)", type(exc).__name__)
                        await warn({"type": "warning", "code": "inference",
                                    "message": "An inference job failed. Check the engine log and available memory; retry or use a smaller model."})
                    finally:
                        busy = False
                        pending.task_done()

            task = asyncio.create_task(worker())
            await send({"type": "ready", "backend": config.backend, "profile": profile,
                        "sampleRate": 16000, "translationDevice": "cpu"})
            connection_open = True
            explicit_stop = False
            last_audio_at = time.monotonic()
            try:
                while True:
                    try:
                        message = await asyncio.wait_for(ws.receive(), timeout=IDLE_TIMEOUT_SECONDS)
                    except TimeoutError:
                        await warn({"type": "warning", "code": "idle",
                                    "message": f"No audio was received for {int(IDLE_TIMEOUT_SECONDS)} seconds. "
                                               "This session was released so a new one can start."})
                        break
                    if message["type"] == "websocket.disconnect":
                        connection_open = False
                        break
                    data = message.get("bytes")
                    if data is not None:
                        if not data or len(data) > 32000 or len(data) % 2:
                            await ws.close(code=1009, reason="Expected at most one second of PCM16 audio")
                            break
                        last_audio_at = time.monotonic()
                        for chunk in segmenter.feed(data):
                            await enqueue(chunk)
                    elif message.get("text"):
                        import json
                        control = json.loads(message["text"])
                        if not isinstance(control, dict):
                            raise ValueError("Expected a control object")
                        if control.get("type") == "ping":
                            await send({"type": "pong"})
                        elif control.get("type") == "reset":
                            segmenter.reset()
                            while not pending.empty():
                                pending.get_nowait()
                                pending.task_done()
                            await send({"type": "reset"})
                        elif control.get("type") == "stop":
                            explicit_stop = True
                            break
                    if time.monotonic() - last_audio_at > AUDIO_GAP_SECONDS:
                        for chunk in segmenter.flush():
                            await enqueue(chunk)
                        last_audio_at = time.monotonic()
            except (WebSocketDisconnect, RuntimeError):
                connection_open = False
            except ValueError:
                with contextlib.suppress(Exception):
                    await ws.close(code=1008, reason="Invalid control message")
            finally:
                # The last phrase only exists inside the segmenter's buffer until
                # the silence gate closes or the stream ends. Without this flush,
                # a video that simply ends never shows its final caption.
                if connection_open and not explicit_stop:
                    for chunk in segmenter.flush():
                        await enqueue(chunk)
                    deadline = time.monotonic() + DRAIN_TIMEOUT_SECONDS
                    while (busy or not pending.empty()) and time.monotonic() < deadline:
                        await asyncio.sleep(0.1)
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError, WebSocketDisconnect, RuntimeError):
                    await task
                # A cancelled HTTP request can leave whisper-server finishing its
                # current job. Its own mutex serializes that job with the next.
    return app
