"""Play short audio cues (a user WAV, or a built-in system sound) without blocking.

Path safety: all user-configured sound file paths are validated before use
to prevent path-traversal, device-file access, and symlink attacks.
"""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
from pathlib import Path

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

# Allowed audio file extensions for user-configured sound paths.
_ALLOWED_AUDIO_EXTS = {".wav", ".mp3", ".ogg", ".oga", ".flac",
                       ".m4a", ".aac", ".aif", ".aiff", ".opus"}

# Directories that user-configured sound paths are allowed to resolve into.
_ALLOWED_PARENTS: tuple[str, ...] = (
    str(Path.home()),
    "/usr/share/sounds",
    "/opt/blitztext",
)


def validate_sound_path(path: str) -> str | None:
    """Validate a user-configured sound file path.

    Returns the resolved absolute path if the file is safe to play,
    or ``None`` if the path is empty, does not exist, or fails any
    security check.

    Checks performed:
      1. Empty / whitespace-only paths are rejected.
      2. ``~user`` is expanded via ``expanduser``.
      3. The path is resolved to an absolute canonical path (``realpath``),
         which eliminates symlinks and ``..`` components.
      4. The resolved path must be a regular file (not a device, FIFO,
         directory, or socket).
      5. The resolved path must reside under one of the allowed parent
         directories (user home, system sounds, or the Blitztext install
         prefix).
      6. The file extension must be a known audio format.
    """
    if not path or not path.strip():
        return None

    expanded = os.path.expanduser(path.strip())
    if not expanded:
        return None

    try:
        resolved = Path(expanded).resolve(strict=False)
    except (OSError, RuntimeError, ValueError):
        return None

    # Must exist and be a regular file.
    if not resolved.exists():
        return None
    try:
        mode = resolved.stat().st_mode
    except OSError:
        return None
    if not stat.S_ISREG(mode):
        return None

    # Must be under an allowed parent directory.
    resolved_str = str(resolved)
    allowed = False
    for parent in _ALLOWED_PARENTS:
        try:
            common = os.path.commonpath([resolved_str, parent])
            if common == parent:
                allowed = True
                break
        except ValueError:
            continue
    if not allowed:
        return None

    # Extension must be a known audio format.
    ext = resolved.suffix.lower()
    if ext not in _ALLOWED_AUDIO_EXTS:
        return None

    return resolved_str


def play(path: str = "", *, fallback: str | None = None) -> "subprocess.Popen | None":
    """Play `path` (WAV/MP3/OGG/FLAC/…); fallback to a freedesktop system sound.

    User-supplied paths are validated via :func:`validate_sound_path` before
    being passed to any audio player.  Invalid or unsafe paths are silently
    ignored (the fallback sound is still attempted).

    Returns the Popen object so callers can terminate a preview, or None.
    """
    target = ""
    if path:
        safe = validate_sound_path(path)
        if safe is not None:
            target = safe
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