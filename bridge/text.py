from __future__ import annotations

import re
import unicodedata


def clean_transcript(text: str) -> str:
    text = re.sub(r"<\|[^|]*\|>", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _normalized(text: str) -> tuple[str, list[int]]:
    letters, ends = [], []
    for i, char in enumerate(text):
        for normalized in unicodedata.normalize("NFKC", char).casefold():
            if unicodedata.category(normalized)[0] in {"L", "N"}:
                letters.append(normalized)
                ends.append(i + 1)
    return "".join(letters), ends


def strip_overlap(previous: str, current: str, *, has_audio_overlap: bool) -> str:
    """Conservative exact suffix-prefix deduplication, only for shared audio.

    We deliberately avoid fuzzy deletion: hallucinated matching can erase real
    repeated words. This heuristic cannot eliminate every boundary duplicate.
    """
    if not has_audio_overlap or not previous:
        return current.strip()
    before, _ = _normalized(previous[-160:])
    after, positions = _normalized(current)
    for n in range(min(100, len(before), len(after)), 2, -1):
        if before.endswith(after[:n]):
            return current[positions[n - 1]:].lstrip(" \t\r\n、。，．！？!?.,;:」』")
    return current.strip()


def join_japanese(previous: str, addition: str, limit: int = 320) -> str:
    if not previous:
        return addition[-limit:]
    separator = " " if previous[-1:].isascii() and addition[:1].isascii() else ""
    result = previous + separator + addition
    # This is a bounded rolling utterance, not unlimited document context.
    return result[-limit:]
