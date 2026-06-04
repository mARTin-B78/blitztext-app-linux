"""Microphone recording by shelling out to a system recorder.

Records 16 kHz mono WAV (what Whisper wants) using whichever recorder is
available — no Python audio bindings or device configuration required.
"""

from __future__ import annotations

import shutil
import signal
import subprocess
import tempfile
from pathlib import Path

# Ordered by preference. Each maps a recorder name to an argv builder.
_RECORDERS: dict[str, list[str]] = {
    "pw-record": ["pw-record", "--rate", "16000", "--channels", "1", "--format", "s16"],
    "parecord": ["parecord", "--rate=16000", "--channels=1", "--format=s16le", "--file-format=wav"],
    "arecord": ["arecord", "-q", "-f", "S16_LE", "-r", "16000", "-c", "1", "-t", "wav"],
}

# How to point each recorder at a specific pactl/pipewire source.
_DEVICE_FLAG: dict[str, list[str]] = {
    "pw-record": ["--target"],
    "parecord": ["-d"],
    "arecord": [],  # ALSA names differ from pactl; fall back to default device
}


def detect_recorder(preference: str = "auto") -> str:
    if preference != "auto":
        if shutil.which(preference):
            return preference
        raise RuntimeError(f"Configured recorder '{preference}' not found on PATH.")
    for name in _RECORDERS:
        if shutil.which(name):
            return name
    raise RuntimeError("No recorder found (need one of: pw-record, parecord, arecord).")


class Recording:
    """A single in-progress recording. Start on construction, call stop()."""

    def __init__(self, recorder: str, device: str = ""):
        self._tmp = Path(tempfile.mkstemp(prefix="blitztext-", suffix=".wav")[1])
        argv = list(_RECORDERS[recorder])
        flag = _DEVICE_FLAG.get(recorder, [])
        if device and flag:
            argv += flag + [device]
        argv += [str(self._tmp)]
        # arecord writes to the file given as a positional arg; the others too.
        self._proc = subprocess.Popen(
            argv,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    def stop(self) -> Path:
        """Stop recording, finalize the WAV, and return its path."""
        if self._proc.poll() is None:
            # SIGINT lets pw-record/arecord flush the WAV header cleanly.
            self._proc.send_signal(signal.SIGINT)
            try:
                self._proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._proc.terminate()
                self._proc.wait(timeout=5)
        return self._tmp

    def discard(self) -> None:
        if self._proc.poll() is None:
            self._proc.terminate()
            self._proc.wait(timeout=5)
        self._tmp.unlink(missing_ok=True)
