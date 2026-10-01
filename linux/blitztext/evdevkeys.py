"""Global key listener reading /dev/input via evdev, for Wayland sessions.

pynput's X11 backend only sees keys while an XWayland window is focused, and
its uinput backend needs root (dumpkeys). Reading evdev needs only membership
of the 'input' group. Keys map by physical position (US layout): fine for
modifiers and most letters, but e.g. z/y are swapped on QWERTZ.

Mirrors the subset of pynput's Listener / GlobalHotKeys API the app uses;
callbacks receive the same string tokens as inputmode._token.
"""

from __future__ import annotations

import os
import select
import threading
import traceback

from .logbuffer import log

_RESCAN_S = 2.0  # hotplug: pick up keyboards connected after start
# Our own key injection (ydotool) must not trigger hotkeys, e.g. Ctrl+V = "stop".
_IGNORED_NAMES = ("ydotoold",)


def _build_tokens() -> dict[int, str]:
    from evdev import ecodes as e

    tokens = {
        e.KEY_LEFTCTRL: "ctrl", e.KEY_RIGHTCTRL: "ctrl",
        e.KEY_LEFTALT: "alt", e.KEY_RIGHTALT: "alt",
        e.KEY_LEFTMETA: "cmd", e.KEY_RIGHTMETA: "cmd",
        e.KEY_LEFTSHIFT: "shift", e.KEY_RIGHTSHIFT: "shift",
        e.KEY_ESC: "esc", e.KEY_SPACE: "space", e.KEY_ENTER: "enter",
        e.KEY_TAB: "tab", e.KEY_BACKSPACE: "backspace", e.KEY_DELETE: "delete",
        e.KEY_INSERT: "insert", e.KEY_HOME: "home", e.KEY_END: "end",
        e.KEY_PAGEUP: "page_up", e.KEY_PAGEDOWN: "page_down",
        e.KEY_UP: "up", e.KEY_DOWN: "down", e.KEY_LEFT: "left", e.KEY_RIGHT: "right",
        e.KEY_MINUS: "-", e.KEY_EQUAL: "=", e.KEY_COMMA: ",", e.KEY_DOT: ".",
        e.KEY_SLASH: "/", e.KEY_SEMICOLON: ";", e.KEY_APOSTROPHE: "'",
        e.KEY_LEFTBRACE: "[", e.KEY_RIGHTBRACE: "]", e.KEY_BACKSLASH: "\\",
        e.KEY_GRAVE: "`",
    }
    for c in "abcdefghijklmnopqrstuvwxyz0123456789":
        tokens[getattr(e, f"KEY_{c.upper()}")] = c
    for n in range(1, 25):
        tokens[getattr(e, f"KEY_F{n}")] = f"f{n}"
    return tokens


_TOKENS: dict[int, str] | None = None


def token(code: int) -> str | None:
    global _TOKENS
    if _TOKENS is None:
        _TOKENS = _build_tokens()
    return _TOKENS.get(code)


def _is_ignored(name: str) -> bool:
    return any(n in name for n in _IGNORED_NAMES)


def _open_keyboards(skip: set[str] = frozenset()) -> list:
    import evdev
    from evdev import ecodes as e

    devices = []
    for path in evdev.list_devices():
        if path in skip:
            continue
        try:
            dev = evdev.InputDevice(path)
        except OSError:  # no permission / vanished
            continue
        keys = dev.capabilities().get(e.EV_KEY, [])
        if _is_ignored(dev.name) or not (e.KEY_A in keys or e.KEY_LEFTCTRL in keys):
            dev.close()
            continue
        devices.append(dev)
    return devices


def keyboards() -> list[str]:
    """Paths of keyboards this process can read."""
    try:
        devs = _open_keyboards()
    except ImportError:
        return []
    paths = [d.path for d in devs]
    for d in devs:
        d.close()
    return paths


def use_evdev() -> bool:
    """True on Wayland when at least one keyboard is readable."""
    if os.environ.get("XDG_SESSION_TYPE", "").lower() != "wayland":
        return False
    if keyboards():
        return True
    log("[WARN]  Wayland: no readable keyboard in /dev/input; global hotkeys only work "
        "in XWayland windows. Fix: sudo usermod -aG input $USER, then log out and in.")
    return False


class Listener:
    """Calls on_press(token) / on_release(token) for every keyboard; ignores autorepeat."""

    def __init__(self, on_press=None, on_release=None):
        self._on_press = on_press
        self._on_release = on_release
        self._thread: threading.Thread | None = None
        self._wake_r, self._wake_w = os.pipe()
        self._stopped = threading.Event()

    # -- pynput-compatible lifecycle -----------------------------------------
    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name="evdev-keys", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stopped.set()
        os.write(self._wake_w, b"x")

    def join(self, timeout: float | None = None) -> None:
        if self._thread is not None:
            self._thread.join(timeout)

    def is_alive(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    # -- event handling -------------------------------------------------------
    def _handle(self, code: int, value: int) -> None:
        if value == 2:  # autorepeat
            return
        tok = token(code)
        if tok is None:
            return
        cb = self._on_press if value == 1 else self._on_release
        if cb is not None:
            try:
                cb(tok)
            except Exception:  # noqa: BLE001 — a bad callback must not kill the listener thread
                log(f"[ERROR] key handler failed:\n{traceback.format_exc()}")

    def _run(self) -> None:
        from evdev import ecodes as e

        devices = {d.fd: d for d in _open_keyboards()}
        try:
            while not self._stopped.is_set():
                ready, _, _ = select.select([self._wake_r, *devices], [], [], _RESCAN_S)
                if not ready:
                    known = {d.path for d in devices.values()}
                    for d in _open_keyboards(skip=known):
                        devices[d.fd] = d
                    continue
                for fd in ready:
                    if fd == self._wake_r:
                        continue
                    dev = devices[fd]
                    try:
                        for ev in dev.read():
                            if ev.type == e.EV_KEY:
                                self._handle(ev.code, ev.value)
                    except OSError:  # unplugged
                        devices.pop(fd).close()
        finally:
            for d in devices.values():
                d.close()
            os.close(self._wake_r)
            os.close(self._wake_w)


class GlobalHotKeys(Listener):
    """pynput.GlobalHotKeys equivalent: fires when exactly the combo is held."""

    def __init__(self, mapping: dict):
        from .inputmode import parse_tokens

        super().__init__(on_press=self._press, on_release=self._release)
        self._combos = [(parse_tokens(spec), cb) for spec, cb in mapping.items()]
        self._held: dict[int, str] = {}  # keycode -> token, so L/R modifiers track separately

    def _handle(self, code: int, value: int) -> None:
        tok = token(code)
        if tok is None or value == 2:
            return
        if value == 1:
            self._held[code] = tok
        else:
            self._held.pop(code, None)
        super()._handle(code, value)

    def _press(self, tok: str) -> None:
        held = set(self._held.values())
        for combo, cb in self._combos:
            if tok in combo and held == combo:
                cb()

    def _release(self, tok: str) -> None:
        pass
