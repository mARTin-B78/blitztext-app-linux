"""Benchmark STT engines against a reference clip.

Given a WAV and its reference transcript, transcribe with each engine, measure
the time, and score accuracy as 1 − WER (word error rate). Used by the Settings
Benchmark tab to find the fastest and most accurate engine/model.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from . import stt
from .routing import normalize


@dataclass
class BenchRow:
    engine: str
    model: str
    ok: bool
    seconds: float
    wer: float
    accuracy: float   # percent, max(0, 1-wer)*100
    text: str
    error: str = ""


def _edit_distance(a: list[str], b: list[str]) -> int:
    m, n = len(a), len(b)
    dp = list(range(n + 1))
    for i in range(1, m + 1):
        prev = dp[0]
        dp[0] = i
        for j in range(1, n + 1):
            cur = dp[j]
            dp[j] = min(dp[j] + 1, dp[j - 1] + 1, prev + (a[i - 1] != b[j - 1]))
            prev = cur
    return dp[n]


def wer(reference: str, hypothesis: str) -> float:
    """Word error rate (0 = perfect). Text is normalized (case/punct-insensitive)."""
    ref = normalize(reference)
    hyp = normalize(hypothesis)
    if not ref:
        return 0.0 if not hyp else 1.0
    return _edit_distance(ref, hyp) / len(ref)


def run(engines, wav_path: Path, reference: str, *, language: str = "",
        get_local_transcriber=None, progress=None) -> list[BenchRow]:
    """Benchmark each engine; calls progress(row) as each finishes."""
    rows: list[BenchRow] = []
    for e in engines:
        tr = get_local_transcriber(e) if (e.is_local and get_local_transcriber) else None
        res = stt.benchmark(e, wav_path, language=language, local_transcriber=tr)
        w = wer(reference, res.text) if res.ok else 1.0
        row = BenchRow(
            engine=e.name,
            model=e.model or ("local" if e.is_local else "(default)"),
            ok=res.ok,
            seconds=res.seconds,
            wer=w,
            accuracy=max(0.0, 1.0 - w) * 100.0,
            text=res.text,
            error=res.error,
        )
        rows.append(row)
        if progress:
            progress(row)
    return rows


def best(rows: list[BenchRow]) -> tuple[BenchRow | None, BenchRow | None]:
    """Return (fastest, most_accurate) among successful rows."""
    ok = [r for r in rows if r.ok]
    if not ok:
        return None, None
    fastest = min(ok, key=lambda r: r.seconds)
    most_accurate = max(ok, key=lambda r: (r.accuracy, -r.seconds))
    return fastest, most_accurate
