from __future__ import annotations

import io
import time
import wave
from collections import deque
from dataclasses import dataclass
from collections.abc import Callable

SAMPLE_RATE = 16000
FRAME_MS = 20
SAMPLES_PER_FRAME = SAMPLE_RATE * FRAME_MS // 1000
FRAME_BYTES = SAMPLES_PER_FRAME * 2
BYTES_PER_SECOND = SAMPLE_RATE * 2


@dataclass(frozen=True)
class Profile:
    max_seconds: float
    silence_ms: int
    overlap_ms: int


PROFILES = {
    "fast": Profile(3.2, 440, 400),
    "balanced": Profile(5.5, 640, 600),
    "context": Profile(8.5, 840, 800),
}


@dataclass
class AudioChunk:
    pcm: bytes
    start_s: float
    end_s: float
    overlap_s: float
    utterance_id: int
    final: bool
    stream_started: float
    generation: int = 0

    @property
    def duration(self) -> float:
        return len(self.pcm) / BYTES_PER_SECOND

    @property
    def new_duration(self) -> float:
        return max(0.02, self.duration - self.overlap_s)

    def to_wav(self) -> bytes:
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(SAMPLE_RATE)
            wav.writeframes(self.pcm)
        return buffer.getvalue()


class Segmenter:
    """Streaming WebRTC VAD with pre-roll, bounded chunks, and overlap.

    A detector can be injected in tests; production uses local WebRTC VAD.
    Audio is never written to disk.
    """

    def __init__(self, profile: str = "balanced", vad_mode: int = 2,
                 detector: Callable[[bytes], bool] | None = None):
        if profile not in PROFILES:
            raise ValueError("Unknown caption profile")
        self.profile = PROFILES[profile]
        if detector is None:
            import webrtcvad
            vad = webrtcvad.Vad(vad_mode)
            def detector(frame):
                return vad.is_speech(frame, SAMPLE_RATE)
        self.detect = detector
        self.generation = -1
        self.reset()

    def reset(self) -> None:
        self.generation += 1
        self.stream_started = time.monotonic()
        self.cursor = 0
        self.remainder = bytearray()
        self.pre: deque[tuple[int, bytes, bool]] = deque(maxlen=15)
        self.frames: list[tuple[int, bytes, bool]] = []
        self.recent: deque[bool] = deque(maxlen=5)
        self.silent_frames = 0
        self.new_voiced = 0
        self.utterance_id = 0
        self.overlap_s = 0.0

    def feed(self, data: bytes) -> list[AudioChunk]:
        if len(data) % 2:
            raise ValueError("PCM16 data must have an even byte length")
        self.remainder.extend(data)
        emitted: list[AudioChunk] = []
        while len(self.remainder) >= FRAME_BYTES:
            frame = bytes(self.remainder[:FRAME_BYTES])
            del self.remainder[:FRAME_BYTES]
            item = (self.cursor, frame, bool(self.detect(frame)))
            self.cursor += 1
            voiced = item[2]
            self.recent.append(voiced)
            if not self.frames:
                self.pre.append(item)
                if len(self.recent) >= 3 and sum(self.recent) >= 3:
                    self.frames = list(self.pre)
                    self.pre.clear()
                    self.new_voiced = sum(f[2] for f in self.frames)
                    self.silent_frames = 0
                continue

            self.frames.append(item)
            if voiced:
                self.new_voiced += 1
                self.silent_frames = 0
            else:
                self.silent_frames += 1

            if self.silent_frames * FRAME_MS >= self.profile.silence_ms:
                # Keep 160 ms of trailing padding, not the entire silence gate.
                trim = max(0, self.silent_frames - 8)
                selected = self.frames[:-trim] if trim else self.frames
                if self.new_voiced >= 12 and selected:
                    emitted.append(self._chunk(selected, final=True))
                self.pre.extend(self.frames[-15:])
                self.frames = []
                self.new_voiced = 0
                self.overlap_s = 0.0
                self.silent_frames = 0
                self.utterance_id += 1
                self.recent.clear()
            elif len(self.frames) * FRAME_MS >= self.profile.max_seconds * 1000:
                if self.new_voiced >= 12:
                    emitted.append(self._chunk(self.frames, final=False))
                keep = max(1, self.profile.overlap_ms // FRAME_MS)
                self.frames = self.frames[-keep:]
                self.overlap_s = len(self.frames) * FRAME_MS / 1000
                self.new_voiced = 0
        return emitted

    def flush(self) -> list[AudioChunk]:
        if self.frames and self.new_voiced >= 12:
            result = [self._chunk(self.frames, final=True)]
        else:
            result = []
        self.frames = []
        self.remainder.clear()
        return result

    def _chunk(self, frames: list[tuple[int, bytes, bool]], final: bool) -> AudioChunk:
        return AudioChunk(
            pcm=b"".join(f[1] for f in frames),
            start_s=frames[0][0] * FRAME_MS / 1000,
            end_s=(frames[-1][0] + 1) * FRAME_MS / 1000,
            overlap_s=self.overlap_s,
            utterance_id=self.utterance_id,
            final=final,
            stream_started=self.stream_started,
            generation=self.generation,
        )
