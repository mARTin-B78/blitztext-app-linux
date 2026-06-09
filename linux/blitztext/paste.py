"""Deliver text into the focused window via xdotool (X11).

Two strategies:
  - "type"  : xdotool types the text directly (no clipboard side effects).
  - "paste" : put text on the clipboard, then send Ctrl+V.

The target window is captured when recording starts and re-activated before
delivery, so a brief focus change during processing doesn't misfire.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time


def _is_wayland() -> bool:
    return os.environ.get("XDG_SESSION_TYPE", "").lower() == "wayland"


def active_window_id() -> str | None:
    if _is_wayland():
        return None  # Wayland compositors don't allow global window ID queries
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
    if window_id and not _is_wayland() and shutil.which("xdotool"):
        subprocess.run(["xdotool", "windowactivate", "--sync", window_id], check=False)
        time.sleep(0.05)


# Above this character count, or when the text contains newlines, xdotool type
# sends thousands of synchronous X11 round-trips and can flood the X11 server's
# per-client event buffer until the whole session freezes.  Auto-upgrade to a
# single clipboard paste instead, which is instantaneous.
_TYPE_THRESHOLD = 300


def deliver(text: str, *, mode: str = "type", window_id: str | None = None, type_delay_ms: int = 4) -> None:
    if not text:
        return

    wayland = _is_wayland()
    if not wayland and not shutil.which("xdotool"):
        raise RuntimeError("xdotool not found; cannot type into the focused window.")
    if wayland and not shutil.which("wtype") and not shutil.which("ydotool"):
        raise RuntimeError("wtype or ydotool not found; cannot type in Wayland session.")

    _focus(window_id)
    # Give the user time to release the hotkey modifiers before we synthesize input.
    time.sleep(0.12)

    # Long or multi-line text: force clipboard paste regardless of configured mode.
    # xdotool type at 12ms/char for a 15 000-char code block takes ~3 minutes and
    # sends so many synchronous X11 events that the server's per-client buffer
    # overflows, freezing the entire X11 session.
    if mode == "type" and (len(text) > _TYPE_THRESHOLD or "\n" in text):
        if _set_clipboard(text):
            mode = "paste"
        # If clipboard isn't available we fall through to xdotool type as before.

    if mode == "paste" and _set_clipboard(text):
        if wayland:
            if shutil.which("wtype"):
                subprocess.run(["wtype", "-M", "ctrl", "v", "-m", "ctrl"], check=False)
            else:
                subprocess.run(["ydotool", "key", "ctrl+v"], check=False)
        else:
            subprocess.run(["xdotool", "key", "--clearmodifiers", "ctrl+v"], check=False)
        return

    if wayland:
        if shutil.which("wtype"):
            subprocess.run(["wtype", "-d", str(type_delay_ms), "--", text], check=False)
        else:
            subprocess.run(["ydotool", "type", "-d", str(type_delay_ms), text], check=False)
    else:
        subprocess.run(
            ["xdotool", "type", "--clearmodifiers", "--delay", str(type_delay_ms), "--", text],
            check=False,
        )


def press_enter(window_id: str | None = None) -> None:
    """Send Return to the focused/target window (auto-send after paste)."""
    wayland = _is_wayland()
    if not wayland and not shutil.which("xdotool"):
        return
    _focus(window_id)
    time.sleep(0.08)
    
    if wayland:
        if shutil.which("wtype"):
            subprocess.run(["wtype", "-k", "Return"], check=False)
        else:
            subprocess.run(["ydotool", "key", "enter"], check=False)
    else:
        subprocess.run(["xdotool", "key", "--clearmodifiers", "Return"], check=False)


def _set_clipboard(text: str) -> bool:
    """Best-effort clipboard set; returns False if no clipboard tool is available."""
    for argv in (["wl-copy"], ["xclip", "-selection", "clipboard"], ["xsel", "--clipboard", "--input"]):
        if shutil.which(argv[0]):
            try:
                subprocess.run(argv, input=text.encode("utf-8"), check=True)
                return True
            except (OSError, subprocess.CalledProcessError):
                continue
    return False
