"""Spoken send: a configured word delivers the clip AND presses Enter.

The spoken equivalent of stop+paste+Enter — mainly hands-free. The keyword is
stripped from the transcript before the rest is delivered and submitted.
"""

import blitztext.daemon as dm
import blitztext.paste as paste
from blitztext.config import Config, Workflow
from blitztext.daemon import Daemon
from blitztext.routing import match_send


# -- matcher --------------------------------------------------------------------
def test_match_send_strips_edges_only():
    kws = ["computer send", "computer abschicken"]
    assert match_send("computer send", kws)[0] == "computer send"        # whole utterance
    kw, text = match_send("hey team the build is green computer send", kws)
    assert kw == "computer send" and text == "hey team the build is green"  # end edge, stripped
    kw, text = match_send("computer send hey team the build is green", kws)
    assert kw == "computer send" and text == "hey team the build is green"  # start edge, stripped
    # A bare word inside a sentence must NOT submit — the phrase is distinctive.
    assert match_send("please send me the report tomorrow", kws)[0] is None
    assert match_send("computer send", [])[0] is None                    # disabled
    assert match_send("", kws)[0] is None


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
    enters = []
    monkeypatch.setattr(paste, "press_enter", lambda win=None: enters.append(win))
    return delivered, enters


def test_process_sends_with_enter_when_send_spoken(monkeypatch, tmp_path):
    delivered, enters = _wire_clean_pipeline(monkeypatch)
    monkeypatch.setattr(dm.stt, "transcribe", lambda *a, **k: "die nachricht ist fertig computer send")
    d = Daemon(Config())
    d._prepared = True
    d.cfg.send_keywords = ["computer send"]
    d.cfg.cancel_keywords = []

    audio = tmp_path / "clip.wav"; audio.write_bytes(b"x")
    d._process(audio, Workflow(name="Transcribe", hotkey="", mode="transcribe"), None)

    assert len(delivered) == 1
    assert delivered[0][0][0] == "die nachricht ist fertig"   # keyword stripped
    assert len(enters) == 1, "send keyword must press Enter"


def test_process_no_enter_without_send_word(monkeypatch, tmp_path):
    """Control: the same path without a send word delivers but never hits Enter."""
    delivered, enters = _wire_clean_pipeline(monkeypatch)
    monkeypatch.setattr(dm.stt, "transcribe", lambda *a, **k: "die nachricht ist fertig")
    d = Daemon(Config())
    d._prepared = True
    d.cfg.send_keywords = ["computer send"]
    d.cfg.cancel_keywords = []

    audio = tmp_path / "clip.wav"; audio.write_bytes(b"x")
    d._process(audio, Workflow(name="Transcribe", hotkey="", mode="transcribe"), None)

    assert len(delivered) == 1
    assert delivered[0][0][0] == "die nachricht ist fertig"
    assert enters == [], "no send word → no Enter"


def test_send_keywords_round_trip(tmp_path):
    from blitztext.config import load, save
    p = tmp_path / "config.toml"
    cfg = load(p)
    assert cfg.send_keywords == []                       # shipped default: off
    cfg.send_keywords = ["computer send", "computer abschicken"]
    save(cfg, p)
    assert load(p).send_keywords == ["computer send", "computer abschicken"]
