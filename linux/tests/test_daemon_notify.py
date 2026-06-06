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
