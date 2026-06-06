"""Play short audio cues (a user WAV, or a built-in system sound) without blocking."""

from __future__ import annotations

import os
import shutil
import subprocess

_FREEDESKTOP = "/usr/share/sounds/freedesktop/stereo/{name}.oga"
_PLAYERS = ("pw-play", "paplay", "aplay")


def play(path: str = "", *, fallback: str | None = None) -> None:
    """Play `path` (a WAV/OGA file); if unset/missing, play the freedesktop
    `fallback` system sound. Returns immediately (fire-and-forget)."""
    target = ""
    if path:
        expanded = os.path.expanduser(path)
        if os.path.exists(expanded):
            target = expanded
    if not target and fallback:
        fd = _FREEDESKTOP.format(name=fallback)
        if os.path.exists(fd):
            target = fd
    if not target:
        return

    # aplay only handles WAV; pw-play/paplay handle WAV + OGA, so try them first.
    for player in _PLAYERS:
        if not shutil.which(player):
            continue
        if player == "aplay" and not target.lower().endswith(".wav"):
            continue
        try:
            subprocess.Popen([player, target], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return
        except OSError:
            continue
