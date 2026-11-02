"""Daemon._process edge paths: STT failure, empty audio, voice cancel/send, whitespace LLM."""
import blitztext.daemon as dm
import blitztext.paste as paste
from blitztext.config import Config, Workflow
from blitztext.daemon import Daemon


def mk(monkeypatch, tmp_path, heard, too_quiet=False, chat=None):
    monkeypatch.setattr(dm, "detect_recorder", lambda pref="auto": "pw-record")
    monkeypatch.setattr(dm, "notify", lambda *a, **k: None)
    monkeypatch.setattr(dm.quality, "analyze_wav", lambda p: (2.0, 0.5))
    monkeypatch.setattr(dm.quality, "too_quiet", lambda *a, **k: too_quiet)
    monkeypatch.setattr(dm.quality, "is_hallucination", lambda *a, **k: False)
    if isinstance(heard, Exception):
        def tr(*a, **k):
            raise heard
        monkeypatch.setattr(dm.stt, "transcribe", tr)
    else:
        monkeypatch.setattr(dm.stt, "transcribe", lambda *a, **k: heard)
    if chat:
        monkeypatch.setattr(dm.llm, "chat", chat)
    out = {"typed": [], "status": [], "enter": [], "text": []}
    monkeypatch.setattr(dm, "deliver", lambda t, **k: out["typed"].append(t))
    monkeypatch.setattr(paste, "press_enter", lambda w=None: out["enter"].append(w))
    d = Daemon(Config(), status_cb=lambda *a: out["status"].append(a))
    d._prepared = True
    d._busy = True
    d.cfg.cancel_keywords = ["abbrechen"]
    d.cfg.send_keywords = ["senden"]
    d.text_cb = out["text"].append
    audio = tmp_path / "c.wav"
    audio.write_bytes(b"x")
    return d, out, audio


def run(d, audio, wf):
    d._process(audio, wf, 7)
    assert not audio.exists() and not d._busy
    return d


TR = Workflow(name="T", hotkey="", mode="transcribe")


def test_stt_failure_reports_error_and_cleans_up(monkeypatch, tmp_path):
    d, out, a = mk(monkeypatch, tmp_path, RuntimeError("stt down"))
    run(d, a, TR)
    assert ("error", "T", "stt down") in out["status"] and out["typed"] == []
    assert out["status"][-1] == ("idle", None, "Ready")


def test_too_quiet_skips_stt(monkeypatch, tmp_path):
    d, out, a = mk(monkeypatch, tmp_path, RuntimeError("must not be called"), too_quiet=True)
    run(d, a, TR)
    assert ("idle", "T", "Too quiet") in out["status"]
    assert not any(s[0] == "error" for s in out["status"])


def test_empty_transcript_no_speech(monkeypatch, tmp_path):
    d, out, a = mk(monkeypatch, tmp_path, "   ")
    run(d, a, TR)
    assert ("idle", "T", "No speech detected") in out["status"] and out["typed"] == []


def test_voice_cancel_discards(monkeypatch, tmp_path):
    d, out, a = mk(monkeypatch, tmp_path, "abbrechen")
    run(d, a, TR)
    assert out["typed"] == [] and ("idle", "T", "Cancelled") in out["status"]
    assert out["text"] == ["✗ Abgebrochen"]


def test_spoken_send_presses_enter(monkeypatch, tmp_path):
    d, out, a = mk(monkeypatch, tmp_path, "hallo welt senden")
    run(d, a, TR)
    assert out["typed"] == ["hallo welt"] and out["enter"] == [7]


def test_abort_during_transcription_drops_result(monkeypatch, tmp_path):
    d, out, a = mk(monkeypatch, tmp_path, "hallo")
    orig = dm.stt.transcribe
    monkeypatch.setattr(dm.stt, "transcribe", lambda *x, **k: (d._abort_event.set(), orig())[1])
    run(d, a, TR)
    assert out["typed"] == []


def test_rewrite_whitespace_only_discarded(monkeypatch, tmp_path):
    wf = Workflow(name="R", hotkey="", mode="rewrite", prompt="P")
    d, out, a = mk(monkeypatch, tmp_path, "hallo welt", chat=lambda *x, **k: "a" + " " * 40)
    run(d, a, wf)
    assert out["typed"] == []
    assert ("error", "R", "LLM returned mostly whitespace — discarded") in out["status"]


def test_rewrite_aborted_by_user(monkeypatch, tmp_path):
    wf = Workflow(name="R", hotkey="", mode="rewrite", prompt="P")

    def chat(*x, **k):
        d._abort_event.set()
        return "result"

    d, out, a = mk(monkeypatch, tmp_path, "hallo welt", chat=chat)
    run(d, a, wf)
    assert out["typed"] == []


def test_rewrite_streams_tokens_to_overlay_window(monkeypatch, tmp_path):
    wf = Workflow(name="R", hotkey="", mode="rewrite", prompt="P")

    def chat(*x, on_token=None, **k):
        on_token("x" * 300)
        on_token("y" * 300)
        return "final text"

    d, out, a = mk(monkeypatch, tmp_path, "hallo welt", chat=chat)
    run(d, a, wf)
    assert out["typed"] == ["final text"]
    assert out["text"][2] == "y" * 300  # window trimmed to <= ~400 chars
