"""Deliver text into the focused window via xdotool (X11).

Two strategies:
  - "type"  : xdotool types the text directly (no clipboard side effects).
  - "paste" : put text on the clipboard, then send Ctrl+V.

The target window is captured when recording starts and re-activated before
delivery, so a brief focus change during processing doesn't misfire.
"""

from __future__ import annotations

import shutil
import subprocess
import time


def active_window_id() -> str | None:
    if not shutil.which("xdotool"):
        return None
    try:
        out = subprocess.run(
            ["xdotool", "getactivewindow"],
            capture_output=True, text=True, check=True,
        )
        return out.stdout.strip() or None
    except (OSError, subprocess.CalledProcessError):
        return None


def _focus(window_id: str | None) -> None:
    if window_id:
        subprocess.run(["xdotool", "windowactivate", "--sync", window_id], check=False)
        time.sleep(0.05)


def deliver(text: str, *, mode: str = "type", window_id: str | None = None, type_delay_ms: int = 4) -> None:
    if not text:
        return
    if not shutil.which("xdotool"):
        raise RuntimeError("xdotool not found; cannot type into the focused window.")

    _focus(window_id)
    # Give the user time to release the hotkey modifiers before we synthesize input.
    time.sleep(0.12)

    if mode == "paste" and _set_clipboard(text):
        subprocess.run(["xdotool", "key", "--clearmodifiers", "ctrl+v"], check=False)
        return

    subprocess.run(
        ["xdotool", "type", "--clearmodifiers", "--delay", str(type_delay_ms), "--", text],
        check=False,
    )


def press_enter(window_id: str | None = None) -> None:
    """Send Return to the focused/target window (auto-send after paste)."""
    if not shutil.which("xdotool"):
        return
    _focus(window_id)
    time.sleep(0.08)
    subprocess.run(["xdotool", "key", "--clearmodifiers", "Return"], check=False)


def _set_clipboard(text: str) -> bool:
    """Best-effort clipboard set; returns False if no clipboard tool is available."""
    for argv in (["xclip", "-selection", "clipboard"], ["xsel", "--clipboard", "--input"], ["wl-copy"]):
        if shutil.which(argv[0]):
            try:
                subprocess.run(argv, input=text.encode("utf-8"), check=True)
                return True
            except (OSError, subprocess.CalledProcessError):
                continue
    return False
