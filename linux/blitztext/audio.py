"""Audio helpers: enumerate input devices and a live input-level meter.

Mic enumeration uses pactl (PipeWire/PulseAudio source names, which pw-record
and parecord accept via --target/-d). The level meter uses sounddevice to read
the chosen input and report a 0..1 level to a callback.
"""

from __future__ import annotations

import shutil
import subprocess
import threading


def list_mics() -> list[tuple[str, str]]:
    """Return [(source_name, friendly_label)] for real input sources.

    The first entry is always the system default ("", "Default device").
    Monitor sources (loopback of outputs) are excluded.
    """
    mics: list[tuple[str, str]] = [("", "Default device")]
    if not shutil.which("pactl"):
        return mics
    try:
        out = subprocess.run(
            ["pactl", "list", "short", "sources"], capture_output=True, text=True, check=True
        ).stdout
    except (OSError, subprocess.CalledProcessError):
        return mics
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        name = parts[1]
        if name.endswith(".monitor"):
            continue
        label = name.replace("alsa_input.", "").replace("-", " ")
        mics.append((name, label))
    return mics


class LevelMeter:
    """Open the given input device and call `on_level(0..1)` periodically."""

    def __init__(self, device: str = "", on_level=None):
        self.device = device or None
        self.on_level = on_level
        self._stream = None
        self._lock = threading.Lock()

    def start(self) -> bool:
        import numpy as np
        import sounddevice as sd

        def _cb(indata, _frames, _time, _status):
            level = float(np.sqrt(np.mean(np.square(indata)))) if indata.size else 0.0
            if self.on_level:
                # Scale RMS (typically small) into a usable 0..1 range.
                self.on_level(min(1.0, level * 12.0))

        try:
            self._stream = sd.InputStream(
                samplerate=16000, channels=1, dtype="float32",
                blocksize=1600, device=self._resolve_device(), callback=_cb,
            )
            self._stream.start()
            return True
        except Exception:  # noqa: BLE001 - device may be busy/unavailable
            self._stream = None
            return False

    def _resolve_device(self):
        # sounddevice wants an index/name it knows; pactl names rarely match, so
        # fall back to the default input when the name isn't resolvable.
        if not self.device:
            return None
        try:
            import sounddevice as sd

            for i, d in enumerate(sd.query_devices()):
                if d["max_input_channels"] > 0 and self.device in d["name"]:
                    return i
        except Exception:  # noqa: BLE001
            pass
        return None

    def stop(self) -> None:
        with self._lock:
            if self._stream is not None:
                try:
                    self._stream.stop()
                    self._stream.close()
                finally:
                    self._stream = None
