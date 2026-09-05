"""Wakeword benchmark: deterministic parts (script, audio decode, framing, scoring).

The network parts (TTS /audio/speech, streaming to wyoming-openwakeword) need
live servers and are exercised manually from Settings → Benchmark; here we cover
everything that can be checked offline.
"""

import io
import json
import random
import wave

import numpy as np

from blitztext import wakeword_bench as wb


def test_wakeword_phrase():
    assert wb.wakeword_phrase("okay_computer") == "okay computer"
    assert wb.wakeword_phrase("hey_jarvis") == "hey jarvis"
    assert wb.wakeword_phrase("models/okay_nabu.tflite") == "okay nabu"
    assert wb.wakeword_phrase("alexa_v0.1") == "alexa"


def test_build_utterances_deterministic_and_covers_voices():
    a = wb.build_utterances("computer", 8, "de", voices=["nova", "onyx"], rng=random.Random(7))
    b = wb.build_utterances("computer", 8, "de", voices=["nova", "onyx"], rng=random.Random(7))
    def key(us):
        return [(u.text, u.has_wakeword, u.voice) for u in us]
    assert key(a) == key(b)                                   # seeded → reproducible
    assert sum(u.has_wakeword for u in a) == 8
    assert all(u.voice in ("nova", "onyx") for u in a)
    assert all("computer" in u.text for u in a if u.has_wakeword)
    assert any(not u.has_wakeword for u in a)                 # filler added for false-fire check


def test_wav_to_pcm_resamples_to_16k_mono():
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(48000)
        n = 48000  # 1.0 s stereo @ 48 kHz
        tone = (np.sin(2 * np.pi * 440 * np.linspace(0, 1, n, endpoint=False)) * 8000).astype("<i2")
        w.writeframes(np.repeat(tone, 2).tobytes())
    pcm = wb._wav_to_pcm16k(buf.getvalue())
    assert len(pcm) == 16000 * 2                              # 1.0 s of 16 kHz mono s16le


def test_drain_detections_handles_payloads():
    det = (json.dumps({"type": "detection", "data": {}}) + "\n").encode()
    chunk = (json.dumps({"type": "audio-chunk", "payload_length": 3}) + "\n").encode() + b"abc"
    rest, n = wb._drain_detections(chunk + det)
    assert n == 1 and rest == b""                             # payload skipped, detection counted
    held = (json.dumps({"type": "x", "payload_length": 10}) + "\n").encode() + b"ab"
    rest2, n2 = wb._drain_detections(held)
    assert n2 == 0 and rest2 == held                          # incomplete payload held, not misparsed


def test_bench_result_metrics():
    r = wb.BenchResult(utterances=[
        wb.Utterance("a", True, "nova", detections=1, ok=True),
        wb.Utterance("b", True, "nova", detections=0, ok=True),
        wb.Utterance("c", True, "onyx", detections=2, ok=True),
        wb.Utterance("d", False, "onyx", detections=1, ok=True),   # false fire
        wb.Utterance("e", True, "x", ok=False, error="boom"),      # failed → excluded
    ])
    assert r.expected == 3 and r.detected == 2
    assert abs(r.recall - 2 / 3) < 1e-9
    assert r.false_fires == 1
    assert r.recall_by_voice() == {"nova": (1, 2), "onyx": (1, 1)}
