"""Benchmark STT engines against a reference clip.

Given a WAV and its reference transcript, transcribe with each engine, measure
the time, and score accuracy as 1 − WER (word error rate). Used by the Settings
Benchmark tab to find the fastest and most accurate engine/model.
"""

from __future__ import annotations

import dataclasses
import re
from dataclasses import dataclass
from pathlib import Path

from . import stt
from .routing import normalize


def _rss_mb() -> float:
    """Current process RSS in MB via /proc/self/status (Linux only)."""
    try:
        with open("/proc/self/status") as fh:
            for line in fh:
                if line.startswith("VmRSS:"):
                    return int(line.split()[1]) / 1024.0  # kB → MB
    except OSError:
        pass
    return 0.0


@dataclass
class BenchRow:
    engine: str
    url: str          # base URL of the engine (empty for local)
    model: str
    device: str       # "CPU" | "CUDA" | "remote"
    best_for: str     # "Short clips" | "Short / medium" | "Long / batch" | "Streaming"
    languages: list[str]  # ISO 639-1 codes from /v1/models, empty if unknown
    ok: bool
    seconds: float
    wer: float
    accuracy: float   # percent, max(0, 1-wer)*100
    text: str
    ram_mb: float = 0.0  # RSS delta in MB; >0 means model loaded during this run
    error: str = ""


def _tokens(text: str, case_sensitive: bool) -> list[str]:
    """Word tokens. case_sensitive keeps capitalisation (and accents); both
    drop punctuation so only the words/spelling are compared."""
    if not case_sensitive:
        return normalize(text)
    return re.sub(r"[^\w\s]", " ", text, flags=re.UNICODE).split()


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


def wer(reference: str, hypothesis: str, *, case_sensitive: bool = False) -> float:
    """Word error rate (0 = perfect). case_sensitive makes capitalisation count."""
    ref = _tokens(reference, case_sensitive)
    hyp = _tokens(hypothesis, case_sensitive)
    if not ref:
        return 0.0 if not hyp else 1.0
    return _edit_distance(ref, hyp) / len(ref)


def _engine_device(engine, transcriber, _cache: dict) -> str:
    if engine.is_local:
        return "CUDA" if getattr(transcriber, "device", "cpu") == "cuda" else "CPU"
    url = engine.url
    if url not in _cache:
        _cache[url] = stt.detect_remote_device(url)
    return _cache[url]


def _engine_best_for(engine) -> str:
    if engine.type == "riva_realtime":
        return "Streaming"
    model = (engine.model or "").lower()
    name = engine.name.lower()
    if any(x in name for x in ("stream", "realtime", "real-time", "live")):
        return "Streaming"
    if engine.is_local:
        if any(x in model for x in ("tiny", "base")):
            return "Short clips"
        if any(x in model for x in ("large",)):
            return "Long / batch"
        return "Short / medium"
    # Remote endpoint
    if any(x in name for x in ("large", "batch")):
        return "Long / batch"
    return "Short / medium"


def run(engines, wav_path: Path, reference: str, *, language: str = "",
        case_sensitive: bool = True, get_local_transcriber=None, progress=None,
        expand_models: bool = False) -> list[BenchRow]:
    """Benchmark each engine; calls progress(row) as each finishes.

    expand_models=True fetches available models for each remote engine and
    runs one benchmark row per model instead of just the configured one.
    Accuracy is case-sensitive by default so wrong capitalisation counts.
    """
    # Build the run list, optionally expanding remote engines by their models
    run_list: list = []
    for e in engines:
        if expand_models and not e.is_local and not e.is_streaming:
            models = stt.list_models(e.url, e.api_key_env)
            if len(models) > 1:
                for m in models:
                    run_list.append(dataclasses.replace(e, model=m,
                                                        name=f"{e.name} [{m}]"))
                continue
        run_list.append(e)

    device_cache: dict = {}
    meta_cache: dict = {}   # url → list[ModelMeta]

    def _get_langs(e) -> list[str]:
        if e.is_local:
            return []
        url = e.url
        if url not in meta_cache:
            meta_cache[url] = stt.list_models_meta(url, e.api_key_env)
        for m in meta_cache[url]:
            if not e.model or m.id == e.model or m.id.endswith("/" + e.model):
                return m.languages
        return meta_cache[url][0].languages if meta_cache[url] else []

    rows: list[BenchRow] = []
    for e in run_list:
        tr = get_local_transcriber(e) if (e.is_local and get_local_transcriber) else None
        rss_before = _rss_mb()
        res = stt.benchmark(e, wav_path, language=language, local_transcriber=tr)
        rss_after = _rss_mb()
        ram_delta = max(0.0, rss_after - rss_before)
        w = wer(reference, res.text, case_sensitive=case_sensitive) if res.ok else 1.0
        row = BenchRow(
            engine=e.name,
            url=e.url,
            model=e.model or ("local" if e.is_local else "(default)"),
            device=_engine_device(e, tr, device_cache),
            best_for=_engine_best_for(e),
            languages=_get_langs(e),
            ok=res.ok,
            seconds=res.seconds,
            wer=w,
            accuracy=max(0.0, 1.0 - w) * 100.0,
            text=res.text,
            ram_mb=ram_delta,
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
