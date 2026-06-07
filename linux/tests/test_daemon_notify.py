"""Hands-free (wakeword) sessions must stay quiet.

Regression tests for two reported bugs:
  1. The wakeword produced desktop notifications when the user was away — most
     notably a "Busy" storm from repeated false detections arriving while a
     previous clip was still transcribing.
  2. A hands-free session's errors popped up as critical notifications.
"""

import blitztext.daemon as daemon_mod
from blitztext.config import Config
from blitztext.daemon import Daemon


def _make_daemon(monkeypatch):
    # Don't probe real audio devices when constructing the daemon.
    monkeypatch.setattr(daemon_mod, "detect_recorder", lambda pref="auto": "pw-record")
    return Daemon(Config())


def test_dnotify_suppressed_in_silent_session(monkeypatch):
    calls = []
    monkeypatch.setattr(daemon_mod, "notify", lambda *a, **k: calls.append((a, k)))
    d = _make_daemon(monkeypatch)

    d._session_silent = True
    d._dnotify("Recording", "…")
    assert calls == [], "per-dictation notifications must be suppressed for hands-free sessions"

    d._session_silent = False
    d._dnotify("Recording", "…")
    assert len(calls) == 1, "keyboard/GUI sessions should still notify"


def test_on_wakeword_starts_a_silent_session(monkeypatch):
    started = {}
    d = _make_daemon(monkeypatch)
    monkeypatch.setattr(d, "start_dictation", lambda wf=None, silent=False: started.update(wf=wf, silent=silent))

    d._on_wakeword()

    assert started.get("silent") is True
    assert started.get("wf") is d._route_workflow


def test_manual_cues_gated_by_master_switch(monkeypatch):
    import blitztext.sound as sound_mod
    plays = []
    monkeypatch.setattr(sound_mod, "play", lambda *a, **k: plays.append((a, k)))
    d = _make_daemon(monkeypatch)
    d._session_silent = False  # manual (keyboard) session

    d.cfg.sounds_enabled = False
    d._play_cue("before")
    d._play_sound("device-removed")
    assert plays == [], "manual cues should be silent when 'Play audio cues' is off"

    d.cfg.sounds_enabled = True
    d._play_cue("before")
    d._play_sound("device-removed")
    assert len(plays) == 2, "manual cues should play when enabled"


def test_wakeword_cues_independent_of_master_switch(monkeypatch):
    """Regression: the manual 'Play audio cues' switch must NOT silence the
    hands-free wakeword sounds (the bug where enabled=false killed the beeps)."""
    import blitztext.sound as sound_mod
    plays = []
    monkeypatch.setattr(sound_mod, "play", lambda *a, **k: plays.append((a, k)))
    d = _make_daemon(monkeypatch)
    d._session_silent = True                 # hands-free session
    d.cfg.sounds_enabled = False             # manual cues off
    d.cfg.wakeword_sound_detected = "/snd/beep_start.wav"
    d.cfg.wakeword_sound_done = "/snd/beep_stop.wav"

    d._play_cue("before")
    d._play_cue("after")
    assert [p[0][0] for p in plays] == ["/snd/beep_start.wav", "/snd/beep_stop.wav"], \
        "wakeword cues must play regardless of the manual master switch"

    # Empty wakeword sound = silent (no system-sound fallback).
    plays.clear()
    d.cfg.wakeword_sound_detected = ""
    d._play_cue("before")
    assert plays == [], "an unset wakeword cue should be silent, not fall back to a system sound"


def test_matched_preset_announced_even_hands_free(monkeypatch):
    """You should see which preset/keyword you triggered, even via the wakeword.
    The routing announcement is gated by notify_routing, NOT by _session_silent."""
    shown = []

    def fake_notify(*a, enabled=True, **k):
        if enabled:
            shown.append(a)

    monkeypatch.setattr(daemon_mod, "notify", fake_notify)
    d = _make_daemon(monkeypatch)
    d._session_silent = True            # hands-free session

    d.cfg.notify_routing = True
    d._rnotify("⚡ Nicer email", "matched: “nicer email”")
    assert shown, "the matched preset must be announced even for hands-free sessions"

    shown.clear()
    d.cfg.notify_routing = False
    d._rnotify("⚡ Nicer email", "matched: “nicer email”")
    assert shown == [], "no announcement when 'Announce matched preset' is off"


def test_wakeword_while_busy_does_not_notify(monkeypatch):
    """The away-from-keyboard "Busy" storm: a detection arriving while the
    previous clip is still being processed must be ignored silently."""
    calls = []
    monkeypatch.setattr(daemon_mod, "notify", lambda *a, **k: calls.append((a, k)))
    d = _make_daemon(monkeypatch)
    d._prepared = True       # model "loaded"
    d._busy = True           # still transcribing the previous clip

    d._on_wakeword()

    assert calls == [], "a wakeword hit while busy must not pop a 'Busy' notification"
    assert d.is_recording is False, "no new session should start while busy"
