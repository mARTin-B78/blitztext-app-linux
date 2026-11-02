"""Daemon: recording control, VAD, streaming, hotkeys, wakeword and failure paths.

All hardware/GTK/threads are faked; nothing touches real config or devices.
"""
import sys
import threading
import types
from pathlib import Path

import pytest

import blitztext.daemon as dm
from blitztext.config import Config, Workflow
from blitztext.daemon import Daemon, _CancelWatcher, _pcm_to_wav


_REAL_VAD_START = Daemon._vad_start


class FakeGLib:
    def __init__(self):
        self.idle, self.timeouts = [], []

    def idle_add(self, fn, *a):
        self.idle.append(fn)
        return 1

    def timeout_add(self, ms, fn, *a):
        self.timeouts.append((ms, fn))
        return 1


@pytest.fixture
def glib(monkeypatch):
    g = FakeGLib()
    repo = types.ModuleType("gi.repository")
    repo.GLib = g
    gi = types.ModuleType("gi")
    gi.repository = repo
    monkeypatch.setitem(sys.modules, "gi", gi)
    monkeypatch.setitem(sys.modules, "gi.repository", repo)
    return g


class FakeRec:
    def __init__(self, *a):
        self.discarded = False

    def stop(self):
        return Path("/nonexistent/clip.wav")

    def discard(self):
        self.discarded = True


class FakeStreamer:
    fail = False

    def __init__(self, engine, **kw):
        self.kw = kw
        self.started = self.stopped = False

    def start(self):
        if FakeStreamer.fail:
            raise RuntimeError("no mic")
        self.started = True

    def stop(self):
        self.stopped = True


@pytest.fixture
def env(monkeypatch, glib):
    FakeStreamer.fail = False
    monkeypatch.setattr(dm, "detect_recorder", lambda pref="auto": "pw-record")
    monkeypatch.setattr(dm, "notify", lambda *a, **k: out["notes"].append((a, k)))
    monkeypatch.setattr(dm, "Recording", FakeRec)
    monkeypatch.setattr(dm, "RivaRealtimeStreamer", FakeStreamer)
    monkeypatch.setattr(dm, "active_window_id", lambda: "win1")
    monkeypatch.setattr(dm, "deliver", lambda t, **k: out["typed"].append((t, k)))
    monkeypatch.setattr(dm.Daemon, "_vad_start", lambda self: out["vad"].append("start"))
    monkeypatch.setattr(dm.Daemon, "_play_cue", lambda self, c: out["cues"].append(c))
    monkeypatch.setattr(dm.Daemon, "_play_sound", lambda self, s: out["sounds"].append(s))
    out = {"notes": [], "typed": [], "status": [], "vad": [], "cues": [], "sounds": []}
    d = Daemon(Config(), status_cb=lambda *a: out["status"].append(a))
    d._prepared = True
    d._process = lambda *a: out.setdefault("proc", a)  # keep thread trivial
    return d, out


def states(out):
    return [s[0] for s in out["status"]]


# -- start / finish / cancel -------------------------------------------------
def test_start_ignored_when_not_ready_or_busy(env):
    d, out = env
    d._prepared = False
    d.start_dictation()
    assert not d.is_recording
    d._prepared = True
    d._busy = True
    d.start_dictation()
    assert not d.is_recording and out["status"] == []


def test_start_records_and_emits(env):
    d, out = env
    d.start_dictation(silent=True)
    assert d.is_recording and d._session_silent
    assert states(out) == ["recording"] and out["vad"] == ["start"]
    d.start_dictation()  # second call ignored while recording
    assert out["vad"] == ["start"]


def test_finish_without_recording_is_noop(env):
    d, out = env
    d.finish_dictation()
    assert out["status"] == [] and not d._busy


def test_finish_spawns_processing(env):
    d, out = env
    d.start_dictation()
    started = threading.Event()
    d._process = lambda *a: (out.setdefault("proc", a), started.set())
    d.finish_dictation(send_enter=True)
    assert started.wait(2)
    assert not d.is_recording and d._busy
    assert out["proc"][3] is True and out["proc"][2] == "win1"
    assert out["cues"] == ["before", "after"]


def test_cancel_recording_discards(env):
    d, out = env
    d.start_dictation()
    rec = d._recording
    d.cancel_dictation()
    assert rec.discarded and not d.is_recording
    assert ("idle", None, "Cancelled") in out["status"]
    assert out["sounds"] == ["device-removed"]


def test_cancel_idle_noop_and_busy_sets_abort(env):
    d, out = env
    d.cancel_dictation()
    assert out["status"] == []
    d._busy = True
    d.cancel_dictation()
    assert d._abort_event.is_set() and ("idle", None, "Cancelled") in out["status"]


def test_toggle_paths(env):
    d, out = env
    wf = Workflow(name="T", hotkey="", mode="transcribe")
    d._prepared = False
    d.toggle(wf)
    assert out["notes"][-1][0][0] == "Please wait"
    d._prepared, d._busy = True, True
    d.toggle(wf)
    assert out["notes"][-1][0][0] == "Busy"
    d._busy = False
    d.toggle(wf)
    assert d.is_recording
    d._process = lambda *a: None
    d.toggle(wf)
    assert not d.is_recording


# -- streaming ---------------------------------------------------------------
def stream_wf():
    return Workflow(name="Live", hotkey="", mode="stream")


def test_stream_requires_streaming_engine(env):
    d, out = env
    d.start_dictation(stream_wf())
    assert not d.is_recording
    assert ("error", "Live", "Active STT engine is not realtime streaming") in out["status"]
    assert out["notes"][-1][0][0] == "Streaming unavailable"


def _streaming_ok(d, monkeypatch):
    monkeypatch.setattr(type(d.cfg), "stt_engine_for",
                        lambda self, wf: types.SimpleNamespace(is_streaming=True))


def test_stream_start_stop_and_enter(env, monkeypatch):
    d, out = env
    _streaming_ok(d, monkeypatch)
    pressed = []
    monkeypatch.setattr("blitztext.paste.press_enter", lambda w=None: pressed.append(w))
    d.start_dictation(stream_wf())
    s = d._streaming
    assert s.started and "streaming" in states(out)
    d.finish_dictation(send_enter=True)
    assert s.stopped and d._streaming is None and pressed == ["win1"]
    assert states(out)[-2:] == ["done", "idle"]


def test_stream_start_failure_resets(env, monkeypatch):
    d, out = env
    _streaming_ok(d, monkeypatch)
    FakeStreamer.fail = True
    d.start_dictation(stream_wf())
    assert d._streaming is None and d._active_workflow is None
    assert ("error", "Live", "no mic") in out["status"]


def test_stream_cancel(env, monkeypatch):
    d, out = env
    _streaming_ok(d, monkeypatch)
    d.start_dictation(stream_wf())
    s = d._streaming
    d.cancel_dictation()
    assert s.stopped and ("idle", None, "Cancelled") in out["status"]


def test_stream_error_callback(env):
    d, out = env
    d._streaming = object()
    d._on_stream_error("Live", RuntimeError("boom"))
    assert d._streaming is None and ("error", "Live", "boom") in out["status"]


def test_stream_text_delivers_stable_prefix_then_final(env):
    d, out = env
    seen = []
    d.text_cb = seen.append
    d._on_stream_text("hello wor", final=False)       # only "hello " is stable
    d._on_stream_text("hello world", final=True)      # remainder + trailing space
    typed = [t for t, _ in out["typed"]]
    assert typed == ["hello ", "world", " "]
    assert d._stream_segment_text == "" and seen[-1] == "hello world"


def test_stream_text_unstable_mismatch_ignored(env):
    d, out = env
    d._stream_segment_text = "abc "
    d._on_stream_text("xyz more", final=False)
    assert out["typed"] == []


def test_stream_language():
    d = Daemon.__new__(Daemon)
    d.cfg = Config()
    for lang, exp in [("en", "en-US"), ("en-GB", "en-GB"), ("de", ""), (None, "")]:
        d.cfg.language = lang
        assert d._stream_language() == exp


# -- VAD / level -------------------------------------------------------------
def test_vad_level_autostop(env, monkeypatch, glib):
    d, out = env
    import time
    t = [1000.0]
    monkeypatch.setattr(time, "time", lambda: t[0])
    d._vad_started_at = d._vad_last_speech = 1000.0
    cd, lv = [], []
    d.countdown_cb = lambda *a: cd.append(a)
    d.level_cb = lv.append
    d._recording = FakeRec()
    d._vad_on_level(0.5, 2.0)                  # speaking
    assert cd[-1] == (None, 2.0) and lv == [0.5]
    t[0] = 1003.0                              # quiet 3s > silence, armed
    d._vad_on_level(0.0, 2.0)
    assert glib.idle and cd[-1][0] == pytest.approx(-1.0)
    called = []
    d.finish_dictation = lambda send_enter=False: called.append(send_enter)
    glib.idle[0]()
    assert called == [False]


def test_vad_not_armed_in_first_two_seconds(env, monkeypatch, glib):
    d, _ = env
    import time
    monkeypatch.setattr(time, "time", lambda: 1001.0)
    d._vad_started_at = d._vad_last_speech = 1000.0
    d._recording = FakeRec()
    d._vad_on_level(0.0, 0.5)
    assert glib.idle == []


def test_vad_stop_stops_components(env):
    d, _ = env
    m, w, a = [types.SimpleNamespace(stopped=False) for _ in range(3)]
    for x in (m, w, a):
        x.stop = lambda x=x: setattr(x, "stopped", True)
    d._vad_meter, d._cancel_watcher, d._action_listener = m, w, a
    d._vad_stop()
    assert m.stopped and w.stopped and a.stopped
    assert d._vad_meter is None and d._cancel_watcher is None and d._action_listener is None


def test_make_cancel_watcher_conditions(env, glib):
    d, _ = env
    d.cfg.cancel_keywords = ["abbrechen"]
    d.cfg.wakeword_cancel_model = ""
    d.transcriber = None
    assert d._make_cancel_watcher() is None
    d.transcriber = object()
    w = d._make_cancel_watcher()
    assert isinstance(w, _CancelWatcher)
    w._on_cancel()
    assert len(glib.idle) == 1
    d.cfg.wakeword_cancel_model = "stop_model"
    assert d._make_cancel_watcher() is None


def test_action_listener_none_without_models(env):
    d, _ = env
    d.cfg.wakeword_enabled = False
    assert d._make_action_listener() is None


def test_action_listener_created(env, monkeypatch):
    d, _ = env
    import blitztext.wakeword as ww
    made = []

    class L:
        def __init__(self, **kw):
            made.append(kw)

        def start(self):
            made.append("started")

    monkeypatch.setattr(ww, "WakewordActionListener", L)
    d.cfg.wakeword_enabled = True
    d.cfg.wakeword_send_model = "send"
    assert d._make_action_listener() is not None
    assert made[-1] == "started" and made[0]["external_audio"] is True


def test_wakeword_action_callbacks(env, glib):
    d, _ = env
    d.cfg.wakeword_cancel_model = "c1, c2"
    d.cfg.wakeword_send_model = "s"
    d.cfg.wakeword_stop_model = ""
    cbs = d._wakeword_action_callbacks()
    assert set(cbs) == {"c1", "c2", "s"}
    calls = []
    d.finish_dictation = lambda send_enter=False: calls.append(send_enter)
    cbs["s"]()
    glib.idle[-1]()
    assert calls == [True]


def test_vad_start_with_failing_meter_schedules_timeout(env, monkeypatch, glib):
    d, _ = env
    monkeypatch.setattr(dm.Daemon, "_vad_start", _REAL_VAD_START)
    import blitztext.audio as audio

    class Meter:
        def __init__(self, *a, **k):
            pass

        def start(self):
            return False

        def stop(self):
            pass

    monkeypatch.setattr(audio, "LevelMeter", Meter)
    d.cfg.wakeword_enabled = False
    d.cfg.cancel_keywords = []
    d._vad_start()
    assert glib.timeouts and glib.timeouts[0][0] == 30_000


def test_vad_start_ok_meter_caps_at_60s(env, monkeypatch, glib):
    d, _ = env
    monkeypatch.setattr(dm.Daemon, "_vad_start", _REAL_VAD_START)
    import blitztext.audio as audio

    class Meter:
        def __init__(self, *a, **k):
            pass

        def start(self):
            return True

        def stop(self):
            pass

    monkeypatch.setattr(audio, "LevelMeter", Meter)
    d.cfg.wakeword_enabled = False
    d.cfg.cancel_keywords = []
    d._vad_start()
    assert glib.timeouts[0][0] == 60_000
    assert glib.timeouts[0][1]() is False  # not recording -> no finish


def test_ov_meter(env, monkeypatch):
    d, _ = env
    d.level_cb = None
    d._ov_meter_start()
    assert d._ov_meter is None
    import blitztext.audio as audio
    started = []

    class Meter:
        def __init__(self, *a, **k):
            pass

        def start(self):
            started.append(1)

        def stop(self):
            started.append("stop")

    monkeypatch.setattr(audio, "LevelMeter", Meter)
    d.level_cb = lambda x: None
    d._ov_meter_start()
    d._ov_meter_stop()
    assert started == [1, "stop"] and d._ov_meter is None


# -- notifications -----------------------------------------------------------
def test_notification_suppression(env):
    d, out = env
    d._session_silent = True
    d._dnotify("x")
    assert out["notes"] == []
    d._session_silent = False
    d._overlay = True
    d._dnotify("x")
    d._rnotify("x")
    assert out["notes"] == []
    d._dnotify("err", urgency="critical")
    assert len(out["notes"]) == 1
    d._overlay = False
    d._rnotify("r")
    assert len(out["notes"]) == 2


def test_emit_swallows_callback_errors(env):
    d, _ = env
    d.status_cb = lambda *a: 1 / 0
    d._emit("idle")


# -- prepare / wakeword ------------------------------------------------------
def test_prepare_remote_engine(env, monkeypatch):
    d, out = env
    d._prepared = False
    monkeypatch.setattr(type(d.cfg), "active_stt",
                        property(lambda s: types.SimpleNamespace(is_local=False, name="srv", url="u")))
    monkeypatch.setattr(d, "_install_freeze_diagnostic", lambda: None)
    d.prepare()
    assert d.ready and d.transcriber is None
    assert out["status"][-1] == ("idle", None, "Ready")


def test_prepare_local_engine_loads_model(env, monkeypatch):
    d, out = env
    d._prepared = False
    made = []
    monkeypatch.setattr(dm, "Transcriber", lambda **kw: made.append(kw) or "T")
    monkeypatch.setattr(type(d.cfg), "active_stt",
                        property(lambda s: types.SimpleNamespace(is_local=True, name="loc", model="tiny", url="")))
    monkeypatch.setattr(d, "_install_freeze_diagnostic", lambda: None)
    d.prepare()
    assert d.transcriber == "T" and made[0]["model"] == "tiny"
    assert states(out)[0] == "loading"


def test_init_wakeword_and_on_wakeword(env, monkeypatch):
    d, _ = env
    import blitztext.wakeword as ww
    made = []

    class L:
        def __init__(self, **kw):
            made.append(kw)

        def start(self):
            made.append("start")

    monkeypatch.setattr(ww, "WakewordListener", L)
    monkeypatch.setattr(ww, "is_muted", lambda: True)
    d.cfg.wakeword_enabled = False
    d._init_wakeword()
    assert made == []
    d.cfg.wakeword_enabled = True
    d.cfg.wakeword_model = "a, b,"
    d._init_wakeword()
    assert made[0]["models"] == ["a", "b"] and made[-1] == "start"
    made[0]["on_detect"]()
    assert d.is_recording and d._session_silent


def test_freeze_diagnostic_registers_handler(env, monkeypatch):
    d, _ = env
    import signal
    reg = {}
    monkeypatch.setattr(signal, "signal", lambda s, h: reg.setdefault(s, h))
    logged = []
    monkeypatch.setattr(dm, "log", logged.append)
    d._install_freeze_diagnostic()
    reg[signal.SIGQUIT](None, None)
    assert "FREEZE DIAGNOSTIC" in logged[0]
    monkeypatch.setattr(signal, "signal", lambda *a: (_ for _ in ()).throw(ValueError()))
    d._install_freeze_diagnostic()  # must not raise


# -- hotkeys / input ---------------------------------------------------------
def test_build_mapping(env):
    d, _ = env
    d.cfg.workflows = [Workflow(name="A", hotkey="<f1>", mode="transcribe"),
                       Workflow(name="B", hotkey="", mode="transcribe")]
    d.cfg.routing_enabled, d.cfg.routing_hotkey = True, "<f2>"
    d.cfg.talk_hotkey = "<f3>"
    m = d._build_mapping()
    assert set(m) == {"<f1>", "<f2>", "<f3>"}
    d.toggle = lambda wf: out_calls.append(wf.name)
    out_calls = []
    m["<f1>"]()
    m["<f2>"]()
    assert out_calls == ["A", "Voice"]


def test_talk_hotkey_runs_in_thread(env, monkeypatch):
    d, _ = env
    import blitztext.talk as talk
    ev = threading.Event()
    monkeypatch.setattr(talk, "play", lambda cfg, cb: ev.set())
    d.cfg.workflows = []
    d.cfg.talk_hotkey = "<f3>"
    d._build_mapping()["<f3>"]()
    assert ev.wait(2)


def test_start_hotkeys_and_stop(env, monkeypatch):
    d, _ = env
    from pynput import keyboard
    seen = {}

    class GH:
        def __init__(self, mapping):
            seen["m"] = mapping
            self.stopped = False

        def start(self):
            seen["started"] = True

        def stop(self):
            self.stopped = True

    monkeypatch.setattr(keyboard, "GlobalHotKeys", GH)
    d.cfg.workflows = [Workflow(name="A", hotkey="<f1>", mode="transcribe")]
    lst = d.start_hotkeys()
    assert seen["started"] and "<f1>" in seen["m"]
    d.stop_hotkeys()
    assert lst.stopped and d._listener is None


def test_start_input_modifiers_mode_and_stop(env, monkeypatch):
    d, _ = env
    import blitztext.inputmode as im
    started = []

    class Scheme:
        def __init__(self, daemon, **kw):
            started.append(kw)

        def start_listener(self):
            return "L"

        def stop_listener(self):
            started.append("stopped")

    monkeypatch.setattr(im, "ModifierScheme", Scheme)
    d.cfg.input_mode = "modifiers"
    d.cfg.workflows = [Workflow(name="A", hotkey="<f1>", mode="transcribe")]
    hk = []
    monkeypatch.setattr(d, "start_hotkeys", lambda: hk.append(1))
    wl = types.SimpleNamespace(stopped=False, stop=lambda: setattr(wl, "stopped", True))
    d._wakeword_listener = wl
    assert d.start_input() == "L" and hk == [1]
    d.stop_input()
    assert "stopped" in started and d._scheme is None and wl.stopped


def test_start_input_combo_mode(env, monkeypatch):
    d, _ = env
    d.cfg.input_mode = "combos"
    monkeypatch.setattr(d, "start_hotkeys", lambda: "HK")
    assert d.start_input() == "HK"


def test_run_headless_joins_and_cleans_up(env, monkeypatch):
    d, out = env
    d.prepare = lambda: None
    seq = []
    lst = types.SimpleNamespace(join=lambda: seq.append("join"))
    d.start_input = lambda: lst
    d.stop_input = lambda: seq.append("stop")
    d.cfg.input_mode = "modifiers"
    d.run()
    assert seq == ["join", "stop"]
    d.cfg.input_mode = "combos"
    seq.clear()
    d.run()
    assert seq == ["join", "stop"]


def test_run_cleans_up_when_join_raises(env):
    d, _ = env
    d.prepare = lambda: None

    def boom():
        raise KeyboardInterrupt

    d.start_input = lambda: types.SimpleNamespace(join=boom)
    stopped = []
    d.stop_input = lambda: stopped.append(1)
    with pytest.raises(KeyboardInterrupt):
        d.run()
    assert stopped == [1]


# -- cancel watcher ----------------------------------------------------------
def test_pcm_to_wav_header(tmp_path):
    p = tmp_path / "a.wav"
    _pcm_to_wav(str(p), b"\x00\x01" * 10)
    b = p.read_bytes()
    assert b[:4] == b"RIFF" and b[8:12] == b"WAVE" and len(b) == 44 + 20


def _watcher(text, hit_log):
    class T:
        def transcribe(self, path, language, beam_size):
            assert Path(path).exists()
            if isinstance(text, Exception):
                raise text
            return text

    return _CancelWatcher(T(), ["abbrechen"], "de", 0.8, lambda: hit_log.append(1))


def test_watcher_cancels_on_keyword():
    hits = []
    w = _watcher("abbrechen", hits)
    w._check(b"\x00" * 100)
    assert hits == [1] and not w._active and not w._checking


def test_watcher_ignores_normal_speech_and_errors():
    hits = []
    _watcher("hallo welt", hits)._check(b"\x00" * 100)
    _watcher(RuntimeError("x"), hits)._check(b"\x00" * 100)
    assert hits == []


def test_watcher_inactive_does_not_fire():
    hits = []
    w = _watcher("abbrechen", hits)
    w.stop()
    w._check(b"\x00" * 100)
    assert hits == []


def test_watcher_feed_thresholds(monkeypatch):
    hits = []
    w = _watcher("hallo", hits)
    started = []
    monkeypatch.setattr(threading.Thread, "start", lambda self: started.append(self))
    w.feed(b"\x00" * 1000)
    assert started == []
    w.feed(b"\x00" * dm._CANCEL_MIN_BYTES)
    assert len(started) == 1 and w._checking
    w.feed(b"\x00" * dm._CANCEL_POLL_BYTES)  # check in flight -> no overlap
    assert len(started) == 1
    w.stop()
    w.feed(b"\x00")
    assert len(started) == 1
