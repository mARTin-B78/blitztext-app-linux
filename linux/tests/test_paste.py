import pytest

from blitztext import paste


@pytest.fixture
def wayland(monkeypatch):
    """GNOME-like Wayland: ydotool + wl-copy, no wtype; records subprocess calls."""
    calls = []
    monkeypatch.setenv("XDG_SESSION_TYPE", "wayland")
    monkeypatch.setattr(paste.time, "sleep", lambda _s: None)
    tools = {"ydotool", "wl-copy"}
    monkeypatch.setattr(paste.shutil, "which", lambda name: f"/usr/bin/{name}" if name in tools else None)
    monkeypatch.setattr(paste.subprocess, "run", lambda argv, **kw: calls.append((argv, kw.get("input"))))
    return calls, tools


def test_ydotool_types_with_layout_keycodes_without_clipboard(wayland, monkeypatch):
    calls, _ = wayland
    monkeypatch.setattr(paste.xkbtype, "gnome_layout", lambda: ("de", "nodeadkeys", ""))
    monkeypatch.setattr(paste.xkbtype, "keystrokes", lambda text, *layout: ["39:1", "39:0"])
    paste.deliver("ö", mode="type", type_delay_ms=12)
    assert calls == [(["ydotool", "key", "-d", "6", "39:1", "39:0"], None)]


def test_ydotool_splits_calls_at_pause(wayland, monkeypatch):
    calls, _ = wayland
    monkeypatch.setattr(paste.xkbtype, "gnome_layout", lambda: ("de", "", ""))
    pause = paste.xkbtype.PAUSE
    monkeypatch.setattr(paste.xkbtype, "keystrokes", lambda text, *layout: ["1:1", pause, "2:1", pause])
    paste.deliver("x", mode="type", type_delay_ms=12)
    assert [argv[4:] for argv, _ in calls] == [["1:1"], ["2:1"]]


def test_ydotool_pastes_when_layout_unknown(wayland, monkeypatch):
    calls, _ = wayland
    monkeypatch.setattr(paste.xkbtype, "gnome_layout", lambda: None)
    paste.deliver("Grüße, schön?", mode="type")
    assert calls[0] == (["wl-copy"], "Grüße, schön?".encode())
    assert calls[1][0] == ["ydotool", "key", "29:1", "47:1", "47:0", "29:0"]
    assert len(calls) == 2


def test_ydotool_falls_back_to_type_without_clipboard(wayland, monkeypatch):
    calls, tools = wayland
    monkeypatch.setattr(paste.xkbtype, "gnome_layout", lambda: None)
    tools.discard("wl-copy")
    paste.deliver("abc", mode="type", type_delay_ms=7)
    assert calls == [(["ydotool", "type", "-d", "7", "abc"], None)]


def test_ydotool_enter_uses_raw_keycodes(wayland):
    calls, _ = wayland
    paste.press_enter()
    assert calls == [(["ydotool", "key", "28:1", "28:0"], None)]


def test_wtype_still_types_directly(wayland):
    calls, tools = wayland
    tools.add("wtype")
    paste.deliver("schön", mode="type", type_delay_ms=4)
    assert calls == [(["wtype", "-d", "4", "--", "schön"], None)]
