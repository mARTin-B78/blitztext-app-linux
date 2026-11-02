"""ModifierScheme state machine with fake daemon and real pynput key objects."""
import pytest

pynput = pytest.importorskip("pynput")
from pynput.keyboard import Key, KeyCode  # noqa: E402

from blitztext import inputmode as im  # noqa: E402


class FakeDaemon:
    def __init__(self):
        self.is_recording = False
        self.calls = []

    def start_dictation(self):
        self.calls.append("start")

    def finish_dictation(self, send_enter):
        self.calls.append(("finish", send_enter))

    def cancel_dictation(self):
        self.calls.append("cancel")


def make(ptt=False):
    d = FakeDaemon()
    s = im.ModifierScheme(d, start="<ctrl>+<cmd>", stop="<ctrl>", send="<alt>",
                          cancel="<esc>", push_to_talk=ptt)
    return s, d


def start(s):
    s._on_press(Key.ctrl_l)
    s._on_press(Key.cmd)


def release_all(s):
    s._on_release(Key.cmd)
    s._on_release(Key.ctrl_l)


def test_parse_tokens():
    assert im.parse_tokens("<ctrl>+<Cmd>") == frozenset({"ctrl", "cmd"})
    assert im.parse_tokens(" <esc> ") == frozenset({"esc"})
    assert im.parse_tokens("") == frozenset()


def test_token_mapping():
    assert im._token(Key.ctrl_r) == "ctrl"
    assert im._token(Key.alt_gr) == "alt"
    assert im._token(Key.shift_l) == "shift"
    assert im._token(Key.esc) == "esc"
    assert im._token(KeyCode.from_char("A")) == "a"
    assert im._token(KeyCode.from_vk(65)) is None
    assert im._token("junk") is None


def test_toggle_start_then_ctrl_stops():
    s, d = make()
    start(s)
    assert d.calls == ["start"]
    s._on_press(Key.ctrl_l)  # still held: not armed yet
    assert d.calls == ["start"]
    release_all(s)
    assert s._state == "armed"
    s._on_press(Key.ctrl_l)
    assert d.calls[-1] == ("finish", False) and s._state == "idle"


def test_alt_sends_enter():
    s, d = make()
    start(s)
    release_all(s)
    s._on_press(Key.alt_l)
    assert d.calls[-1] == ("finish", True)


def test_other_key_while_armed_ignored():
    s, d = make()
    start(s)
    release_all(s)
    s._on_press(KeyCode.from_char("x"))
    assert d.calls == ["start"] and s._state == "armed"


def test_cancel_while_recording_via_wakeword():
    s, d = make()
    s._on_press(Key.esc)
    assert d.calls == []  # idle and not recording: ignored
    s._on_release(Key.esc)
    d.is_recording = True
    s._on_press(Key.esc)
    assert d.calls == ["cancel"]


def test_cancel_while_arming():
    s, d = make()
    start(s)
    s._on_press(Key.esc)
    assert d.calls == ["start", "cancel"] and s._state == "idle"


def test_stale_modifier_does_not_start():
    s, d = make()
    s._pressed.add("ctrl")  # missed release
    s._on_press(Key.cmd)
    assert d.calls == []


def test_ptt_release_stops():
    s, d = make(ptt=True)
    start(s)
    s._on_release(Key.cmd)
    assert d.calls[-1] == ("finish", False) and s._state == "idle"


def test_unknown_key_ignored():
    s, d = make()
    s._on_press(KeyCode.from_vk(1))
    s._on_release(KeyCode.from_vk(1))
    assert d.calls == [] and s._pressed == set()


def test_listener_lifecycle(monkeypatch):
    s, _ = make()
    created = []

    class L:
        def __init__(self, **kw):
            created.append(self)
            self.started = self.stopped = False

        def start(self):
            self.started = True

        def stop(self):
            self.stopped = True

    monkeypatch.setattr(pynput.keyboard, "Listener", L)
    l = s.start_listener()
    assert l.started and s._listener is l
    s.stop_listener()
    assert l.stopped and s._listener is None
    s.stop_listener()  # idempotent
