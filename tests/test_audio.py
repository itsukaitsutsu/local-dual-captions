import struct
import wave
from io import BytesIO

import pytest

from bridge.audio import FRAME_BYTES, PROFILES, Segmenter

VOICE = struct.pack("<h", 1200) * (FRAME_BYTES // 2)
SILENCE = bytes(FRAME_BYTES)


def detector(frame):
    return frame != SILENCE


def segmenter(profile="balanced"):
    return Segmenter(profile, detector=detector)


def test_silence_produces_no_caption_job():
    s = segmenter()
    assert s.feed(SILENCE * 600) == []
    assert s.flush() == []


def test_brief_click_is_not_speech():
    s = segmenter()
    assert s.feed(SILENCE * 15 + VOICE * 4 + SILENCE * 60) == []


def test_pause_finishes_phrase_and_wav_is_correct():
    s = segmenter()
    chunks = s.feed(SILENCE * 15 + VOICE * 50 + SILENCE * 40)
    assert len(chunks) == 1
    chunk = chunks[0]
    assert chunk.final
    assert chunk.overlap_s == 0
    assert 1.0 < chunk.duration < 1.6
    with wave.open(BytesIO(chunk.to_wav())) as wav:
        assert wav.getframerate() == 16000
        assert wav.getnchannels() == 1
        assert wav.getsampwidth() == 2
        assert wav.readframes(wav.getnframes()) == chunk.pcm


@pytest.mark.parametrize("profile", PROFILES)
def test_continuous_speech_has_bounded_overlapping_windows(profile):
    s = segmenter(profile)
    chunks = s.feed(VOICE * 1050 + SILENCE * 60)
    assert len(chunks) >= 3
    for chunk in chunks:
        assert chunk.duration <= PROFILES[profile].max_seconds + .001
        assert chunk.new_duration > 0
    for previous, current in zip(chunks, chunks[1:], strict=False):
        assert current.start_s < previous.end_s
        assert current.overlap_s == pytest.approx(PROFILES[profile].overlap_ms / 1000)
        n = int(current.overlap_s * 32000)
        assert current.pcm[:n] == previous.pcm[-n:]
    assert chunks[-1].final


def test_new_phrase_does_not_claim_shared_audio():
    s = segmenter()
    a = s.feed(VOICE * 50 + SILENCE * 50)
    b = s.feed(VOICE * 50 + SILENCE * 50)
    assert a[0].utterance_id != b[0].utterance_id
    assert b[0].overlap_s == 0


def test_fragmented_pcm_and_reset():
    pcm = VOICE * 40 + SILENCE * 45
    s = segmenter()
    result = []
    for offset in range(0, len(pcm), 222):
        result.extend(s.feed(pcm[offset:offset + 222]))
    assert len(result) == 1
    generation = s.generation
    s.reset()
    assert s.generation == generation + 1
    assert s.cursor == 0
    with pytest.raises(ValueError):
        s.feed(b"x")
