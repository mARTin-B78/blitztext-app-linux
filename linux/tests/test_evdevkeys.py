from evdev import ecodes as e

from blitztext import evdevkeys
from blitztext.evdevkeys import GlobalHotKeys, Listener
from blitztext.inputmode import ModifierScheme

PRESS, RELEASE, REPEAT = 1, 0, 2


def test_token_mapping():
    assert evdevkeys.token(e.KEY_LEFTCTRL) == "ctrl"
    assert evdevkeys.token(e.KEY_RIGHTCTRL) == "ctrl"
    assert evdevkeys.token(e.KEY_RIGHTALT) == "alt"
    assert evdevkeys.token(e.KEY_LEFTMETA) == "cmd"
    assert evdevkeys.token(e.KEY_ESC) == "esc"
    assert evdevkeys.token(e.KEY_SPACE) == "space"
    assert evdevkeys.token(e.KEY_E) == "e"
    assert evdevkeys.token(e.KEY_5) == "5"
    assert evdevkeys.token(e.KEY_F9) == "f9"
    assert evdevkeys.token(e.KEY_VOLUMEUP) is None


def test_listener_forwards_press_release_and_drops_repeat():
    got = []
    lst = Listener(on_press=lambda t: got.append(("p", t)), on_release=lambda t: got.append(("r", t)))
    lst._handle(e.KEY_LEFTCTRL, PRESS)
    lst._handle(e.KEY_LEFTCTRL, REPEAT)
    lst._handle(e.KEY_LEFTCTRL, RELEASE)
    lst._handle(e.KEY_VOLUMEUP, PRESS)
    assert got == [("p", "ctrl"), ("r", "ctrl")]


def _hk(mapping):
    return GlobalHotKeys(mapping)


def test_hotkey_fires_on_exact_combo():
    fired = []
    hk = _hk({"<ctrl>+<alt>+e": lambda: fired.append("e")})
    for code in (e.KEY_LEFTCTRL, e.KEY_LEFTALT, e.KEY_E):
        hk._handle(code, PRESS)
    assert fired == ["e"]
    hk._handle(e.KEY_E, REPEAT)
    assert fired == ["e"]


def test_hotkey_named_key_and_extra_key_blocks():
    fired = []
    hk = _hk({"<ctrl>+<alt>+<space>": lambda: fired.append(1)})
    for code in (e.KEY_LEFTSHIFT, e.KEY_LEFTCTRL, e.KEY_LEFTALT, e.KEY_SPACE):
        hk._handle(code, PRESS)
    assert fired == []  # shift held too -> not an exact match
    hk._handle(e.KEY_LEFTSHIFT, RELEASE)
    hk._handle(e.KEY_SPACE, RELEASE)
    hk._handle(e.KEY_SPACE, PRESS)
    assert fired == [1]


def test_left_and_right_modifier_release_tracked_per_key():
    fired = []
    hk = _hk({"<ctrl>+e": lambda: fired.append(1)})
    hk._handle(e.KEY_LEFTCTRL, PRESS)
    hk._handle(e.KEY_RIGHTCTRL, PRESS)
    hk._handle(e.KEY_LEFTCTRL, RELEASE)  # right ctrl still held
    hk._handle(e.KEY_E, PRESS)
    assert fired == [1]


class _FakeDaemon:
    is_recording = False

    def __init__(self):
        self.calls = []

    def start_dictation(self):
        self.calls.append("start")

    def finish_dictation(self, send_enter):
        self.calls.append(("finish", send_enter))

    def cancel_dictation(self):
        self.calls.append("cancel")


def test_modifier_scheme_accepts_string_tokens():
    d = _FakeDaemon()
    s = ModifierScheme(d, start="<ctrl>+<cmd>", stop="<ctrl>", send="<alt>", cancel="<esc>")
    s._on_press("ctrl")
    s._on_press("cmd")
    s._on_release("cmd")
    s._on_release("ctrl")
    s._on_press("alt")
    assert d.calls == ["start", ("finish", True)]


def test_virtual_devices_are_skipped():
    assert evdevkeys._is_ignored("ydotoold virtual device")
    assert not evdevkeys._is_ignored("Cherry GmbH CHERRY Corded Device")


def test_backend_selection(monkeypatch):
    monkeypatch.setenv("XDG_SESSION_TYPE", "x11")
    assert not evdevkeys.use_evdev()
    monkeypatch.setenv("XDG_SESSION_TYPE", "wayland")
    monkeypatch.setattr(evdevkeys, "keyboards", lambda: ["/dev/input/event3"])
    assert evdevkeys.use_evdev()
    monkeypatch.setattr(evdevkeys, "keyboards", list)
    assert not evdevkeys.use_evdev()
