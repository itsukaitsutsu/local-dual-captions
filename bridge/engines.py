from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import httpx

from .audio import AudioChunk
from .text import clean_transcript


@dataclass
class Recognition:
    text: str
    segments: list[dict]


class WhisperEngine:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")
        self.client = httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=3.0), trust_env=False)

    async def ready(self) -> bool:
        try:
            response = await self.client.get(self.base_url + "/health", timeout=3.0)
            return response.status_code == 200 and response.json().get("status") == "ok"
        except (httpx.HTTPError, ValueError):
            return False

    async def transcribe(self, chunk: AudioChunk, prompt: str = "") -> Recognition:
        # whisper-server reads controls as multipart fields, not URL encoding.
        fields = {
            "language": "ja", "translate": "false", "response_format": "verbose_json",
            "temperature": "0.0", "temperature_inc": "0.0", "beam_size": "1",
            "best_of": "1", "no_timestamps": "false", "token_timestamps": "false",
            "no_language_probabilities": "true", "suppress_nst": "true",
            "prompt": prompt[-120:],
        }
        files = {name: (None, value) for name, value in fields.items()}
        files["file"] = ("live.wav", chunk.to_wav(), "audio/wav")
        response = await self.client.post(self.base_url + "/inference", files=files)
        response.raise_for_status()
        result = response.json()
        segments = result.get("segments", [])
        kept = []
        for segment in segments:
            if segment.get("no_speech_prob", 0) > 0.8 and segment.get("avg_logprob", 0) < -0.8:
                continue
            kept.append(segment)
        text = "".join(s.get("text", "") for s in kept) if segments else result.get("text", "")
        return Recognition(clean_transcript(text), kept)

    async def close(self) -> None:
        await self.client.aclose()


class JapaneseTranslator:
    """Run OPUS-MT JA→EN weights in CTranslate2, fully locally.

    No Transformers/PyTorch dependency and no runtime download. SentencePiece
    input includes Marian's EOS token; a separate target tokenizer decodes
    output. Short rolling utterances provide limited context, not LLM-level
    document understanding or a guarantee of correct meaning.
    """

    def __init__(self, package_path: str | Path, threads: int = 4):
        import ctranslate2
        import sentencepiece

        path = Path(package_path)
        required = [path / name for name in ("model.bin", "source.spm", "target.spm", "config.json")]
        if not all(p.is_file() for p in required):
            raise FileNotFoundError("OPUS-MT Japanese translation files are missing. Run Setup.ps1 again.")
        self.source = sentencepiece.SentencePieceProcessor(model_file=str(path / "source.spm"))
        self.target = sentencepiece.SentencePieceProcessor(model_file=str(path / "target.spm"))
        self.translator = ctranslate2.Translator(
            str(path), device="cpu", compute_type="int8", inter_threads=1, intra_threads=threads,
        )

    @lru_cache(maxsize=64)
    def translate(self, text: str) -> str:
        text = text.strip()
        if not text:
            return ""
        sentences = [s.strip() for s in re.split(r"(?<=[。！？!?])\s*", text) if s.strip()]
        batches = [self.source.encode(s, out_type=str) + ["</s>"] for s in sentences]
        results = self.translator.translate_batch(
            batches, beam_size=4, num_hypotheses=1, replace_unknowns=True,
            max_input_length=0, max_decoding_length=384,
        )
        return " ".join(self.target.decode(result.hypotheses[0]).strip() for result in results).strip()
