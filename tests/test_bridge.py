import asyncio
import json
import struct

import httpx
import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from bridge.app import create_app
from bridge.audio import AudioChunk, FRAME_BYTES
from bridge.config import Config
from bridge.engines import Recognition, WhisperEngine

KEY = "a-test-pairing-key-with-at-least-32-characters"
ORIGIN = "chrome-extension://" + "a" * 32
SILENCE = bytes(FRAME_BYTES)
VOICE = struct.pack("<h", 1500) * (FRAME_BYTES // 2)


class FakeEngine:
    def __init__(self):
        self.closed = False
        self.calls = 0

    async def ready(self):
        return True

    async def transcribe(self, chunk, prompt=""):
        self.calls += 1
        return Recognition("今日はいい天気ですね。", [])

    async def close(self):
        self.closed = True


class FakeTranslator:
    def translate(self, text):
        return "It is a beautiful day today."


def make_app():
    config = Config(token=KEY, engine_secret="s" * 40)
    return create_app(config, engine=FakeEngine(), translator=FakeTranslator(),
                      detector_factory=lambda: lambda frame: frame != SILENCE)


def test_http_status_requires_key_and_never_returns_engine_secret():
    with TestClient(make_app()) as client:
        assert client.get("/health").json()["service"] == "Local Dual Captions"
        assert client.get("/status").status_code == 401
        response = client.get("/status", headers={"X-Caption-Key": KEY, "Origin": ORIGIN})
        assert response.status_code == 200
        assert response.json()["ready"]
        assert "engine_secret" not in response.text
        assert response.headers["access-control-allow-origin"] == ORIGIN
        assert client.get("/health", headers={"host": "attacker.example"}).status_code == 400


def test_webpage_origin_cannot_open_websocket():
    with TestClient(make_app()) as client:
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect("/live", headers={"origin": "https://example.com"}):
                pass


def test_incorrect_key_cannot_stream_audio():
    with TestClient(make_app()) as client:
        with client.websocket_connect("/live", headers={"origin": ORIGIN}) as ws:
            ws.send_json({"type": "hello", "token": "wrong"})
            with pytest.raises(WebSocketDisconnect) as exc:
                ws.receive_json()
            assert exc.value.code == 1008


def test_audio_to_two_phase_bilingual_caption_and_reset():
    app = make_app()
    with TestClient(app) as client:
        with client.websocket_connect("/live", headers={"origin": ORIGIN}) as ws:
            ws.send_json({"type": "hello", "token": KEY, "profile": "fast", "vadMode": 2})
            assert ws.receive_json()["type"] == "ready"
            pcm = VOICE * 35 + SILENCE * 30
            for offset in range(0, len(pcm), 16000):
                ws.send_bytes(pcm[offset:offset + 16000])
            first = ws.receive_json()
            second = ws.receive_json()
            assert first["type"] == second["type"] == "caption"
            assert first["translating"] is True
            assert second["translating"] is False
            assert first["ja"] == second["ja"] == "今日はいい天気ですね。"
            assert second["en"] == "It is a beautiful day today."
            assert second["lagMs"] >= 0
            ws.send_json({"type": "reset"})
            assert ws.receive_json()["type"] == "reset"
            ws.send_json({"type": "ping"})
            assert ws.receive_json()["type"] == "pong"
            ws.send_json({"type": "stop"})
    assert app.state.engine.closed


def test_oversized_audio_message_is_rejected():
    with TestClient(make_app()) as client:
        with client.websocket_connect("/live", headers={"origin": ORIGIN}) as ws:
            ws.send_json({"type": "hello", "token": KEY})
            assert ws.receive_json()["type"] == "ready"
            ws.send_bytes(bytes(32002))
            with pytest.raises(WebSocketDisconnect) as exc:
                ws.receive_json()
            assert exc.value.code == 1009


def test_single_active_session():
    with TestClient(make_app()) as client:
        with client.websocket_connect("/live", headers={"origin": ORIGIN}) as first:
            first.send_json({"type": "hello", "token": KEY})
            assert first.receive_json()["type"] == "ready"
            with client.websocket_connect("/live", headers={"origin": ORIGIN}) as second:
                second.send_json({"type": "hello", "token": KEY})
                assert second.receive_json()["type"] == "error"
            first.send_json({"type": "stop"})


def test_whisper_controls_are_multipart_and_translation_is_off():
    async def run():
        def handle(request):
            body = request.content.decode("latin1")
            assert 'name="language"\r\n\r\nja' in body
            assert 'name="translate"\r\n\r\nfalse' in body
            assert 'name="response_format"\r\n\r\nverbose_json' in body
            assert "RIFF" in body and "WAVE" in body
            return httpx.Response(200, json={"text": "今日は晴れです。", "segments": [
                {"text": "今日は晴れです。", "no_speech_prob": .05, "avg_logprob": -.1}]})
        engine = WhisperEngine("http://127.0.0.1:8178/engine-private")
        await engine.client.aclose()
        engine.client = httpx.AsyncClient(transport=httpx.MockTransport(handle))
        chunk = AudioChunk(VOICE * 30, 0, .6, 0, 0, True, 0)
        assert (await engine.transcribe(chunk)).text == "今日は晴れです。"
        await engine.close()
    asyncio.run(run())


def test_manifest_has_no_remote_inference_endpoints():
    from pathlib import Path
    manifest = json.loads((Path(__file__).parents[1] / "extension" / "manifest.json").read_text())
    assert manifest["manifest_version"] == 3
    assert manifest["host_permissions"] == ["http://127.0.0.1/*"]
    assert "https:" not in manifest["content_security_policy"]["extension_pages"]
    assert "nativeMessaging" not in manifest["permissions"]
