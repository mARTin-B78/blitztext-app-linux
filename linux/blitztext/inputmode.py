"""Modifier-key input scheme (whisper-key style), as an alternative to combos.

Default interaction:
  Ctrl+Win  start recording
  Ctrl      stop -> transcribe -> paste
  Alt       stop -> transcribe -> paste -> Enter (auto-send)
  Esc       cancel (discard, no transcription)

Bare modifier taps are risky (a stray Ctrl+C could misfire), so stop/send/cancel
are only armed *while recording* and only after the start modifiers are released.
A push-to-talk variant records while the start chord is held and stops on release.

Uses a low-level pynput Listener (press/release), not GlobalHotKeys.
"""

from __future__ import annotations


def _token(key) -> str | None:
    """Canonical token for a pynput key: ctrl/alt/cmd/shift/esc or a char."""
    from pynput import keyboard

    if isinstance(key, keyboard.Key):
        name = key.name
        for mod in ("ctrl", "alt", "cmd", "shift"):
            if name.startswith(mod):
                return mod
        return name  # 'esc', 'space', 'enter', ...
    if isinstance(key, keyboard.KeyCode) and key.char:
        return key.char.lower()
    return None


def parse_tokens(spec: str) -> frozenset[str]:
    """'<ctrl>+<cmd>' -> {'ctrl','cmd'};  '<ctrl>' -> {'ctrl'}."""
    return frozenset(p.strip().strip("<>").lower() for p in spec.split("+") if p.strip())


class ModifierScheme:
    def __init__(self, daemon, *, start: str, stop: str, send: str, cancel: str, push_to_talk: bool = False):
        self.daemon = daemon
        self.start = parse_tokens(start)
        self.stop = parse_tokens(stop)
        self.send = parse_tokens(send)
        self.cancel = parse_tokens(cancel)
        self.ptt = push_to_talk
        self._pressed: set[str] = set()
        self._state = "idle"          # idle | arming | armed
        self._listener = None

    # -- listener lifecycle ---------------------------------------------------
    def start_listener(self):
        from pynput import keyboard

        self._listener = keyboard.Listener(on_press=self._on_press, on_release=self._on_release)
        self._listener.start()
        return self._listener

    def stop_listener(self) -> None:
        if self._listener is not None:
            self._listener.stop()
            self._listener = None

    # -- event handling -------------------------------------------------------
    def _is(self, token: str, combo: frozenset[str]) -> bool:
        # A single-token trigger fires on that token; a chord needs all tokens held.
        if len(combo) == 1:
            return token in combo
        return combo.issubset(self._pressed)

    def _on_press(self, key) -> None:
        token = _token(key)
        if token is None:
            return
        self._pressed.add(token)

        if self._state == "idle":
            if self.start.issubset(self._pressed):
                self._state = "arming"
                self.daemon.start_dictation()
            return

        # Cancel works while arming or armed.
        if self._is(token, self.cancel):
            self._state = "idle"
            self.daemon.cancel_dictation()
            return

        if self._state == "armed":
            if self._is(token, self.send):
                self._state = "idle"
                self.daemon.finish_dictation(send_enter=True)
            elif self._is(token, self.stop):
                self._state = "idle"
                self.daemon.finish_dictation(send_enter=False)

    def _on_release(self, key) -> None:
        token = _token(key)
        if token is not None:
            self._pressed.discard(token)

        if self._state != "arming":
            return
        if self.ptt:
            # Push-to-talk: releasing the start chord stops and pastes.
            if not self.start.issubset(self._pressed):
                self._state = "idle"
                self.daemon.finish_dictation(send_enter=False)
        else:
            # Toggle: arm stop/send once the start modifiers are all released.
            if not (self._pressed & self.start):
                self._state = "armed"
