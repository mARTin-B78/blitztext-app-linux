"""Spoken abort: a cancel word discards a clip before it is acted on.

Rescues accidentally triggered (e.g. wakeword) dictations — the transcript is
recognised but nothing is routed, rewritten, or typed.
"""

import blitztext.daemon as dm
from blitztext.config import Config, Workflow
from blitztext.daemon import Daemon
from blitztext.routing import is_cancel


# -- matcher --------------------------------------------------------------------
def test_is_cancel_matches_edges_only():
    kws = ["abbrechen", "cancel"]
    assert is_cancel("abbrechen", kws) == "abbrechen"                 # whole utterance
    assert is_cancel("ok das ganze bitte abbrechen", kws) == "abbrechen"  # end edge
    assert is_cancel("cancel this please", kws) == "cancel"           # start edge
    assert is_cancel("abbrechn", ["abbrechen"]) == "abbrechen"        # ASR drift, fuzzy
    # Word buried mid-sentence must NOT cancel a legitimate dictation.
    assert is_cancel("ich will den vorgang abbrechen weil es spaet ist", ["abbrechen"]) is None
    assert is_cancel("hallo welt", ["abbrechen"]) is None
    assert is_cancel("abbrechen", []) is None                         # disabled
    assert is_cancel("", ["abbrechen"]) is None


def test_cancel_keywords_round_trip(tmp_path):
    from blitztext.config import load, save
    p = tmp_path / "config.toml"
    cfg = load(p)
    assert cfg.cancel_keywords == ["abbrechen", "cancel"]   # shipped default
    cfg.cancel_keywords = ["nein doch nicht", "scrap that"]
    save(cfg, p)
    assert load(p).cancel_keywords == ["nein doch nicht", "scrap that"]


# -- pipeline -------------------------------------------------------------------
def _wire_clean_pipeline(monkeypatch):
    monkeypatch.setattr(dm, "detect_recorder", lambda pref="auto": "pw-record")
    monkeypatch.setattr(dm, "notify", lambda *a, **k: None)
    monkeypatch.setattr(dm.quality, "analyze_wav", lambda p: (2.0, 0.5))
    monkeypatch.setattr(dm.quality, "too_quiet", lambda *a, **k: False)
    monkeypatch.setattr(dm.quality, "clean", lambda t, **k: t)
    monkeypatch.setattr(dm.quality, "is_hallucination", lambda *a, **k: False)
    delivered = []
    monkeypatch.setattr(dm, "deliver", lambda *a, **k: delivered.append((a, k)))
    return delivered


def test_process_discards_when_cancel_spoken(monkeypatch, tmp_path):
    delivered = _wire_clean_pipeline(monkeypatch)
    monkeypatch.setattr(dm.stt, "transcribe", lambda *a, **k: "ok das ganze bitte abbrechen")
    d = Daemon(Config())
    d._prepared = True
    d.cfg.cancel_keywords = ["abbrechen", "cancel"]

    audio = tmp_path / "clip.wav"
    audio.write_bytes(b"x")
    d._process(audio, Workflow(name="Transcribe", hotkey="", mode="transcribe"), None)

    assert delivered == [], "a voice-cancelled clip must never be typed"
    assert not audio.exists(), "the temp clip is still cleaned up afterwards"
    assert d._busy is False


def test_process_delivers_without_cancel_word(monkeypatch, tmp_path):
    """Control: the same path with no cancel word still types normally."""
    delivered = _wire_clean_pipeline(monkeypatch)
    monkeypatch.setattr(dm.stt, "transcribe", lambda *a, **k: "hallo welt")
    d = Daemon(Config())
    d._prepared = True
    d.cfg.cancel_keywords = ["abbrechen", "cancel"]

    audio = tmp_path / "clip.wav"
    audio.write_bytes(b"x")
    d._process(audio, Workflow(name="Transcribe", hotkey="", mode="transcribe"), None)

    assert len(delivered) == 1, "a normal clip must still be delivered"
    assert delivered[0][0][0] == "hallo welt"
