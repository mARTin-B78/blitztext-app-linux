"""Play short audio cues (a user WAV, or a built-in system sound) without blocking."""

from __future__ import annotations

import os
import shutil
import subprocess

_FREEDESKTOP = "/usr/share/sounds/freedesktop/stereo/{name}.oga"

# (player, extra_args, wav_only)
# Ordered: native PipeWire/PulseAudio first, then ffplay/gst as universal fallback.
_PLAYERS: list[tuple[str, list[str], bool]] = [
    ("pw-play",      [],                                          False),
    ("paplay",       [],                                          False),
    ("aplay",        [],                                          True),   # WAV only
    ("ffplay",       ["-nodisp", "-autoexit", "-loglevel", "quiet"], False),
    ("gst-play-1.0", [],                                          False),
]
_NATIVE_EXTS = {".wav", ".oga", ".ogg", ".flac"}


def play(path: str = "", *, fallback: str | None = None) -> "subprocess.Popen | None":
    """Play `path` (WAV/MP3/OGG/FLAC/…); fallback to a freedesktop system sound.

    Returns the Popen object so callers can terminate a preview, or None.
    """
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
        return None

    ext = os.path.splitext(target)[1].lower()
    for player, extra, wav_only in _PLAYERS:
        if not shutil.which(player):
            continue
        if wav_only and ext != ".wav":
            continue
        if player == "paplay" and ext not in _NATIVE_EXTS:
            continue
        try:
            proc = subprocess.Popen(
                [player] + extra + [target],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            return proc
        except OSError:
            continue
    return None
