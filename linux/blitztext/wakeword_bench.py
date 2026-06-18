"""Benchmark the wakeword detector with synthetic speech.

Generates short utterances — random filler text with the wakeword spoken in it,
plus pure-filler utterances with no wakeword — synthesizes each in a random voice
via the *same* (OpenAI-compatible) endpoint configured for speech-to-text, then
streams the audio to the running wyoming-openwakeword server and counts what it
detects. Reports:

  • recall      — share of wakeword utterances that fired at least one detection
  • false fires — detections during pure-filler utterances (should be zero)
  • per-voice recall, so you can see which voices your model handles

TTS reuses the STT engine on purpose: on a typical NIM/OpenAI-compatible setup
the same server answers ``/audio/speech``, so there's nothing extra to configure
beyond a TTS model id and a voice list.
"""

from __future__ import annotations

import io
import json
import os
import random
import socket
import time
import urllib.error
import urllib.request
import wave
from dataclasses import dataclass, field
from urllib.parse import urlparse

# Bilingual filler so the synthesized speech is sentence-like (the detector sees
# realistic context around the wakeword, not just the bare phrase). Unknown
# languages fall back to English text — the voice still speaks it in its accent.
_FILLERS = {
    "en": [
        "the weather today is unusually calm and bright",
        "remind me to call the office before noon",
        "i think the train leaves around half past nine",
        "could you put the report on my desk later",
        "we should grab a coffee once this is done",
        "the package was delivered to the wrong address again",
    ],
    "de": [
        "das wetter ist heute ungewöhnlich ruhig und klar",
        "erinnere mich daran das büro vor mittag anzurufen",
        "ich glaube der zug fährt gegen halb zehn",
        "könntest du den bericht später auf meinen tisch legen",
        "wir sollten einen kaffee trinken wenn das erledigt ist",
        "das paket wurde wieder an die falsche adresse geliefert",
    ],
}

# OpenAI's stock voices; a sensible default for any OpenAI-compatible TTS. Local
# servers (Kokoro, openedai-speech, …) expose their own names — override in the
# config / Settings to match what your endpoint actually serves.
DEFAULT_VOICES = ["alloy", "echo", "fable", "onyx", "nova", "shimmer"]

_TARGET_RATE = 16000          # wyoming-openwakeword expects 16 kHz mono s16le
_CHUNK_BYTES = 3200           # 100 ms per audio-chunk, matching the live listener


@dataclass
class Utterance:
    text: str
    has_wakeword: bool
    voice: str
    detections: int = 0
    ok: bool = False          # synthesized + streamed without error
    error: str = ""


@dataclass
class BenchResult:
    utterances: list[Utterance] = field(default_factory=list)
    seconds: float = 0.0

    @property
    def wake(self) -> list[Utterance]:
        return [u for u in self.utterances if u.has_wakeword]

    @property
    def filler(self) -> list[Utterance]:
        return [u for u in self.utterances if not u.has_wakeword]

    @property
    def detected(self) -> int:
        return sum(1 for u in self.wake if u.ok and u.detections > 0)

    @property
    def expected(self) -> int:
        return sum(1 for u in self.wake if u.ok)

    @property
    def recall(self) -> float:
        return self.detected / self.expected if self.expected else 0.0

    @property
    def false_fires(self) -> int:
        return sum(u.detections for u in self.filler if u.ok)

    def recall_by_voice(self) -> dict[str, tuple[int, int]]:
        """voice -> (detected, expected) over wakeword utterances."""
        out: dict[str, list[int]] = {}
        for u in self.wake:
            if not u.ok:
                continue
            d = out.setdefault(u.voice, [0, 0])
            d[1] += 1
            if u.detections > 0:
                d[0] += 1
        return {v: (d[0], d[1]) for v, d in out.items()}


def wakeword_phrase(model: str) -> str:
    """Turn a wakeword model id into the phrase to speak (best effort).

    "okay_computer" -> "okay computer", "hey_jarvis" -> "hey jarvis". Strips a
    trailing version/format suffix like "_v0.1" or ".tflite".
    """
    name = model.rsplit("/", 1)[-1]
    for ext in (".tflite", ".onnx"):
        if name.endswith(ext):
            name = name[: -len(ext)]
    name = name.replace("_", " ").replace("-", " ")
    # Drop a trailing token that is just a version like "v0.1".
    parts = [p for p in name.split() if not (p.startswith("v") and any(c.isdigit() for c in p))]
    return " ".join(parts).strip() or name.strip()


def _filler_pool(language: str) -> list[str]:
    lang = (language or "").lower()
    if lang.startswith("de"):
        return _FILLERS["de"]
    return _FILLERS["en"]


def build_utterances(phrase: str, count: int, language: str, *,
                     filler_count: int | None = None, voices=None,
                     rng: random.Random | None = None) -> list[Utterance]:
    """Build `count` wakeword utterances + `filler_count` pure-filler ones.

    Each wakeword utterance embeds `phrase` at the start, middle, or end of a
    random filler sentence; voices are assigned round-robin-ish at random so the
    set covers every configured voice. Deterministic when `rng` is seeded.
    """
    rng = rng or random.Random()
    voices = list(voices or DEFAULT_VOICES) or DEFAULT_VOICES
    pool = _filler_pool(language)
    if filler_count is None:
        filler_count = max(3, count // 3)

    def a_voice() -> str:
        return rng.choice(voices)

    out: list[Utterance] = []
    for _ in range(count):
        filler = rng.choice(pool)
        where = rng.choice(("start", "end", "mid"))
        if where == "start":
            text = f"{phrase}, {filler}"
        elif where == "end":
            text = f"{filler}, {phrase}"
        else:
            words = filler.split()
            cut = len(words) // 2
            text = " ".join(words[:cut] + [phrase] + words[cut:])
        out.append(Utterance(text=text, has_wakeword=True, voice=a_voice()))
    for _ in range(filler_count):
        out.append(Utterance(text=rng.choice(pool), has_wakeword=False, voice=a_voice()))
    rng.shuffle(out)
    return out


# --- TTS via an OpenAI-compatible /audio/speech endpoint ---------------------
def _auth_headers(api_key_env: str) -> dict:
    key = os.environ.get(api_key_env or "", "")
    return {"Authorization": f"Bearer {key}"} if key else {}


def synthesize(tts_url: str, text: str, *, model: str, voice: str,
               api_key_env: str = "", timeout: float = 30.0) -> bytes:
    """Return 16 kHz mono s16le PCM for `text` from an OpenAI-compatible TTS.

    `tts_url` is the base incl. /v1 (e.g. http://localhost:8880/v1). Asks for WAV
    and resamples whatever rate/-channels come back down to 16 kHz mono.
    """
    base = (tts_url or "").rstrip("/")
    if not base:
        raise RuntimeError("No TTS URL configured (Settings → Benchmark → TTS URL).")
    payload = json.dumps({
        "model": model, "input": text, "voice": voice, "response_format": "wav",
    }).encode("utf-8")
    headers = {"Content-Type": "application/json", **_auth_headers(api_key_env)}
    req = urllib.request.Request(base + "/audio/speech", data=payload, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:200]
        raise RuntimeError(f"TTS HTTP {exc.code}: {detail}") from exc
    except (urllib.error.URLError, OSError) as exc:
        raise RuntimeError(f"TTS request failed: {exc}") from exc
    return _wav_to_pcm16k(raw)


def list_voices(tts_url: str, *, api_key_env: str = "", timeout: float = 8.0) -> list[str]:
    """Best-effort voice discovery (Kokoro/XTTS expose /audio/voices or /voices).

    Returns [] if the server has no such endpoint — voices are then entered by
    hand. Accepts the common shapes: ["a", …], {"voices": …}, {"data": [{id}…]}.
    """
    base = (tts_url or "").rstrip("/")
    if not base:
        return []
    for path in ("/audio/voices", "/voices"):
        try:
            req = urllib.request.Request(base + path, headers=_auth_headers(api_key_env))
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read())
        except Exception:  # noqa: BLE001 - endpoint optional/non-standard
            continue
        items = data.get("voices") or data.get("data") or [] if isinstance(data, dict) else data
        out: list[str] = []
        for it in items or []:
            if isinstance(it, str):
                out.append(it)
            elif isinstance(it, dict):
                name = it.get("id") or it.get("name") or it.get("voice")
                if name:
                    out.append(str(name))
        if out:
            return out
    return []


def probe(tts_url: str, *, model: str, voice: str, api_key_env: str = "",
          timeout: float = 20.0) -> tuple[bool, str]:
    """Connectivity check: synthesize one short phrase. Returns (ok, message)."""
    try:
        pcm = synthesize(tts_url, "connection test", model=model, voice=voice,
                         api_key_env=api_key_env, timeout=timeout)
    except Exception as exc:  # noqa: BLE001 - surface the reason to the user
        return False, str(exc)
    return True, f"Connected — “{voice}” returned {len(pcm) / 2 / _TARGET_RATE:.1f}s of audio."


def _wav_to_pcm16k(wav_bytes: bytes) -> bytes:
    """Decode a WAV blob to 16 kHz mono signed-16 PCM (linear resample)."""
    import numpy as np  # type: ignore[import-untyped]

    with wave.open(io.BytesIO(wav_bytes), "rb") as w:
        ch, width, rate, n = w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()
        frames = w.readframes(n)
    if width != 2:
        raise RuntimeError(f"Unexpected TTS sample width {width*8}-bit (need 16-bit WAV).")
    a = np.frombuffer(frames, dtype=np.int16).astype(np.float32)
    if ch > 1:
        a = a.reshape(-1, ch).mean(axis=1)
    if rate != _TARGET_RATE and a.size:
        new_len = int(round(a.size * _TARGET_RATE / rate))
        if new_len > 0:
            xp = np.linspace(0.0, 1.0, num=a.size, endpoint=False)
            x = np.linspace(0.0, 1.0, num=new_len, endpoint=False)
            a = np.interp(x, xp, a)
    return np.clip(a, -32768, 32767).astype("<i2").tobytes()


# --- wyoming-openwakeword detection ------------------------------------------
def count_detections(uri: str, model: str, pcm: bytes, *, settle: float = 1.5,
                     timeout: float = 15.0) -> int:
    """Stream `pcm` (16 kHz mono s16le) to wyoming-openwakeword; count detections.

    Sends a fresh detect/audio-start/…/audio-stop session, then drains detection
    events until the server falls quiet for `settle` seconds (or `timeout`).
    """
    parsed = urlparse(uri)
    host, port = parsed.hostname or "127.0.0.1", parsed.port or 10400
    deadline = time.time() + timeout
    detections = 0
    with socket.create_connection((host, port), timeout=5.0) as sock:
        _send(sock, {"type": "detect", "data": {"names": [model]}})
        _send(sock, {"type": "audio-start", "data": {"rate": 16000, "width": 2, "channels": 1}})
        for i in range(0, len(pcm), _CHUNK_BYTES):
            chunk = pcm[i:i + _CHUNK_BYTES]
            _send(sock, {"type": "audio-chunk",
                         "data": {"rate": 16000, "width": 2, "channels": 1},
                         "payload_length": len(chunk)}, chunk)
        _send(sock, {"type": "audio-stop", "data": {}})
        sock.settimeout(settle)
        buf = b""
        while time.time() < deadline:
            try:
                data = sock.recv(4096)
            except socket.timeout:
                break  # server quiet for `settle`s → done
            if not data:
                break
            buf += data
            buf, n = _drain_detections(buf)
            detections += n
    return detections


def _send(sock: socket.socket, msg: dict, payload: bytes = b"") -> None:
    sock.sendall((json.dumps(msg) + "\n").encode("utf-8"))
    if payload:
        sock.sendall(payload)


def _drain_detections(buf: bytes) -> tuple[bytes, int]:
    """Parse whole newline-framed messages from buf; return (rest, detections).

    Consumes each message's binary payload too, so payload bytes are never
    mistaken for the next header line.
    """
    found = 0
    if b"\n" not in buf and len(buf) > 65536:
        raise ValueError("Line length exceeded 64KB")
    while b"\n" in buf:
        line, rest = buf.split(b"\n", 1)
        if len(line) > 65536:
            raise ValueError("Line length exceeded 64KB")
        try:
            msg = json.loads(line.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return rest, found
        plen = msg.get("payload_length", 0) or 0
        if plen > 10 * 1024 * 1024:
            raise ValueError(f"Payload length {plen} exceeded 10MB")
        if len(rest) < plen:
            return buf, found  # payload not fully arrived yet; wait for more
        rest = rest[plen:]
        if msg.get("type") == "detection":
            found += 1
        buf = rest
    return buf, found


@dataclass
class EngineRun:
    """One wakeword engine's benchmark result."""
    name: str
    uri: str
    model: str
    result: BenchResult


def run(engines, *, tts_url: str, tts_model: str, tts_api_key_env: str = "", voices=None,
        language: str = "", count: int = 12, seed: int | None = None,
        progress=None) -> list[EngineRun]:
    """Benchmark each wakeword engine against the same synthesized speech.

    `engines` is a list of objects with ``.name`` / ``.uri`` / ``.model`` (e.g.
    ``config.WakewordEngine``). Each engine is scored on `count` utterances of
    its own wake phrase (+ filler). Audio is synthesized once per (text, voice)
    and reused across engines that share a phrase, so adding engines is cheap.
    Calls ``progress(engine_idx, engine_total, engine_name, done, total, u)``.
    """
    cache: dict[tuple[str, str], bytes] = {}
    runs: list[EngineRun] = []
    n_eng = len(engines)
    for ei, eng in enumerate(engines, 1):
        phrase = wakeword_phrase(eng.model)
        utterances = build_utterances(phrase, count, language, voices=voices, rng=random.Random(seed))
        res = BenchResult(utterances=utterances)
        total = len(utterances)
        t0 = time.time()
        for ui, u in enumerate(utterances, 1):
            try:
                key = (u.text, u.voice)
                pcm = cache.get(key)
                if pcm is None:
                    pcm = synthesize(tts_url, u.text, model=tts_model, voice=u.voice,
                                     api_key_env=tts_api_key_env)
                    cache[key] = pcm
                u.detections = count_detections(eng.uri, eng.model, pcm)
                u.ok = True
            except Exception as exc:  # noqa: BLE001 - record per-utterance, keep going
                u.error = str(exc)
            if progress:
                progress(ei, n_eng, eng.name or eng.model, ui, total, u)
        res.seconds = time.time() - t0
        runs.append(EngineRun(eng.name or eng.model, eng.uri, eng.model, res))
    return runs
