"""Transcription quality gate: reject silence, too-short clips, and the stock
Whisper hallucinations that appear on (near-)silent audio.

Ported in spirit from the macOS app's TranscriptionQualityService. Pure stdlib
(no audioop, which is gone in 3.13): RMS is computed from the WAV samples.
"""

from __future__ import annotations

import array
import math
import re
import wave
from pathlib import Path

# Phrases Whisper commonly invents on silence / noise, across languages.
_HALLUCINATIONS = {
    "thank you", "thank you.", "thanks for watching", "thanks for watching.",
    "thank you for watching", "please subscribe", "you", "bye", "bye.", ".", "...",
    "vielen dank", "vielen dank.", "tschuss", "danke", "danke schon",
    "untertitel von stephanie geiges", "untertitelung des zdf",
    "untertitel im auftrag des zdf", "amara org", "subtitles by",
}


def analyze_wav(path: Path) -> tuple[float, float]:
    """Return (duration_seconds, rms) for a 16-bit PCM WAV. rms is 0..32767."""
    try:
        with wave.open(str(path), "rb") as w:
            frames = w.getnframes()
            rate = w.getframerate() or 16000
            width = w.getsampwidth()
            raw = w.readframes(frames)
    except (wave.Error, OSError, EOFError):
        return 0.0, 0.0

    duration = frames / rate if rate else 0.0
    if width != 2 or not raw:
        return duration, 0.0

    samples = array.array("h")
    samples.frombytes(raw[: len(raw) - (len(raw) % 2)])
    if not samples:
        return duration, 0.0
    rms = math.sqrt(sum(s * s for s in samples) / len(samples))
    return duration, rms


def too_quiet(duration: float, rms: float, *, min_seconds: float, silence_rms: float) -> bool:
    return duration < min_seconds or rms < silence_rms


def _norm(text: str) -> str:
    t = text.lower().strip()
    t = re.sub(r"[^\w\s]", " ", t, flags=re.UNICODE)
    return re.sub(r"\s+", " ", t).strip()


def is_hallucination(text: str, duration: float) -> bool:
    """True if the text is a known artifact — only treated as such for short clips."""
    norm = _norm(text)
    if not norm:
        return True
    if duration <= 2.5 and norm in _HALLUCINATIONS:
        return True
    # A very short clip that produced only a stock phrase is suspect too.
    if duration <= 1.5 and len(norm.split()) <= 2 and norm in _HALLUCINATIONS:
        return True
    return False


def clean(text: str, *, strip_trailing_punctuation: bool = False) -> str:
    text = text.strip()
    if strip_trailing_punctuation:
        text = text.rstrip(" .,!?;:")
    return text
