"""Characterization tests for Daemon._process: routing, rewrite and failure paths."""

import blitztext.daemon as dm
import blitztext.paste as paste
from blitztext.config import Config, Workflow
from blitztext.daemon import Daemon
from blitztext.llm import LLMError


def _daemon(monkeypatch, heard, chat):
    monkeypatch.setattr(dm, "detect_recorder", lambda pref="auto": "pw-record")
    monkeypatch.setattr(dm, "notify", lambda *a, **k: None)
    monkeypatch.setattr(dm.quality, "analyze_wav", lambda p: (2.0, 0.5))
    monkeypatch.setattr(dm.quality, "too_quiet", lambda *a, **k: False)
    monkeypatch.setattr(dm.quality, "clean", lambda t, **k: t)
    monkeypatch.setattr(dm.quality, "is_hallucination", lambda *a, **k: False)
    monkeypatch.setattr(dm.stt, "transcribe", lambda *a, **k: heard)
    monkeypatch.setattr(dm.llm, "chat", chat)
    out = {"delivered": [], "enters": [], "status": [], "text": [], "routed": []}
    monkeypatch.setattr(dm, "deliver", lambda t, **k: out["delivered"].append(t))
    monkeypatch.setattr(paste, "press_enter", lambda win=None: out["enters"].append(win))
    d = Daemon(Config(), status_cb=lambda *a: out["status"].append(a))
    d._prepared = True
    d.cfg.cancel_keywords = []
    d.cfg.send_keywords = []
    d.cfg.workflows = [
        Workflow(name="Transcribe", hotkey="", mode="transcribe"),
        Workflow(name="Mail", hotkey="", mode="rewrite", prompt="P", keywords=["email"],
                 model="m1", temperature=0.1, icon="✉"),
    ]
    d.text_cb = out["text"].append
    d.routing_cb = lambda *a: out["routed"].append(a)
    return d, out


def _run(d, tmp_path, mode="route"):
    audio = tmp_path / "clip.wav"
    audio.write_bytes(b"x")
    d._process(audio, Workflow(name="Route", hotkey="", mode=mode), 42)
    assert not audio.exists()
    return d


def test_route_then_rewrite_delivers_llm_text(monkeypatch, tmp_path):
    calls = []

    def chat(engine, prompt, text, **kw):
        calls.append((prompt, text, kw["model"], kw["temperature"]))
        kw["on_token"]("Sehr ")
        kw["on_token"]("geehrte")
        return "Sehr geehrte Damen"

    d, out = _daemon(monkeypatch, "email hallo welt", chat)
    _run(d, tmp_path)
    assert calls == [("P", "hallo welt", "m1", 0.1)]
    assert out["delivered"] == ["Sehr geehrte Damen"]
    assert out["routed"] == [("✉", "Mail", "email")]
    assert out["text"][:3] == ["📝 hallo welt", "Sehr ", "Sehr geehrte"]
    states = [s[0] for s in out["status"]]
    assert ("done", "Mail", "Sehr geehrte Damen") in out["status"]
    assert states[-1] == "idle" and out["status"][-1] == ("idle", None, "Ready")


def test_route_keyword_only_stops(monkeypatch, tmp_path):
    d, out = _daemon(monkeypatch, "email", lambda *a, **k: "x")
    _run(d, tmp_path)
    assert out["delivered"] == []
    assert ("idle", "Mail", "Only a keyword heard") in out["status"]


def test_rewrite_llm_error(monkeypatch, tmp_path):
    def chat(*a, **k):
        raise LLMError("down")

    d, out = _daemon(monkeypatch, "email text", chat)
    _run(d, tmp_path)
    assert out["delivered"] == []
    assert ("error", "Mail", "down") in out["status"]
    assert out["text"][-1] == "✗ down"


def test_rewrite_unexpected_error(monkeypatch, tmp_path):
    def chat(*a, **k):
        raise ValueError("bad")

    d, out = _daemon(monkeypatch, "email text", chat)
    _run(d, tmp_path)
    assert ("error", "Mail", "LLM error: bad") in out["status"]
    assert out["text"][-1] == "✗ LLM error: bad"


def test_rewrite_whitespace_rejected(monkeypatch, tmp_path):
    d, out = _daemon(monkeypatch, "email text", lambda *a, **k: "a        \n\n      ")
    _run(d, tmp_path)
    assert out["delivered"] == []
    msg = "LLM returned mostly whitespace — discarded"
    assert ("error", "Mail", msg) in out["status"]


def test_route_without_keyword_uses_default_and_stop_word(monkeypatch, tmp_path):
    d, out = _daemon(monkeypatch, "hallo welt fertig", lambda *a, **k: "never")
    d.cfg.stop_keywords = ["fertig"]
    _run(d, tmp_path)
    assert out["delivered"] == ["hallo welt"]
    assert out["enters"] == []
    assert out["routed"] and out["routed"][0][2] in (None, "")


def test_transcribe_exception_reports_error(monkeypatch, tmp_path):
    d, out = _daemon(monkeypatch, "", lambda *a, **k: "")

    def boom(*a, **k):
        raise RuntimeError("stt down")

    monkeypatch.setattr(dm.stt, "transcribe", boom)
    _run(d, tmp_path, mode="transcribe")
    assert ("error", "Route", "stt down") in out["status"]


def test_empty_transcript_no_speech(monkeypatch, tmp_path):
    d, out = _daemon(monkeypatch, "", lambda *a, **k: "")
    _run(d, tmp_path, mode="transcribe")
    assert ("idle", "Route", "No speech detected") in out["status"]
    assert out["delivered"] == []


def test_action_listener_callbacks(monkeypatch):
    import blitztext.wakeword as ww
    created = {}

    class FakeListener:
        def __init__(self, uri, model_callbacks, mic, external_audio):
            created.update(uri=uri, cbs=model_callbacks, mic=mic, ext=external_audio)

        def start(self):
            created["started"] = True

    monkeypatch.setattr(ww, "WakewordActionListener", FakeListener)
    d, _ = _daemon(monkeypatch, "", lambda *a, **k: "")
    d.cfg.wakeword_enabled = True
    d.cfg.wakeword_cancel_model = "stop_it, abbruch ,"
    d.cfg.wakeword_send_model = "send"
    d.cfg.wakeword_stop_model = ""
    listener = d._make_action_listener()
    assert isinstance(listener, FakeListener) and created["started"] and created["ext"] is True
    assert list(created["cbs"]) == ["stop_it", "abbruch", "send"]
    d.cfg.wakeword_enabled = False
    assert d._make_action_listener() is None


def test_overlay_token_cb_schedules_thinking_pulse_via_glib(monkeypatch):
    import sys
    import types
    calls = []
    glib = types.SimpleNamespace(idle_add=lambda fn: calls.append(fn))
    gi = types.ModuleType("gi")
    repo = types.ModuleType("gi.repository")
    repo.GLib = glib
    gi.repository = repo
    monkeypatch.setitem(sys.modules, "gi", gi)
    monkeypatch.setitem(sys.modules, "gi.repository", repo)
    d = _daemon(monkeypatch, "x", lambda *a, **k: "y")[0]
    d.text_cb = lambda t: None
    d._overlay_token_cb()
    assert len(calls) == 1
