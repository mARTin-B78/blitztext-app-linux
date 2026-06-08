"""Audio helpers: enumerate input devices and a live input-level meter.

Mic enumeration uses pactl (PipeWire/PulseAudio source names, which pw-record
and parecord accept via --target/-d). The level meter shells out to the same
system recorder the app uses (pw-record/parecord/arecord), reading raw PCM from
its stdout and reporting a 0..1 level to a callback — no Python audio binding,
so it works wherever the recorder does (PortAudio/sounddevice can't open the
default input on some PipeWire systems).
"""

from __future__ import annotations

import shutil
import subprocess
import threading

from .recorder import detect_recorder

# Raw-PCM (s16le, 16 kHz mono) variants of the recorders, streamed to stdout so
# we can RMS each chunk directly. Mirrors recorder.py's WAV commands but emits
# headerless PCM. pw-record/parecord default to stdout; arecord uses "-t raw".
_METER_ARGV: dict[str, list[str]] = {
    "pw-record": ["pw-record", "--rate=16000", "--channels=1", "--format=s16", "-"],
    "parecord": ["parecord", "--rate=16000", "--channels=1", "--format=s16le"],
    "arecord": ["arecord", "-q", "-f", "S16_LE", "-r", "16000", "-c", "1", "-t", "raw"],
}

# How to point each recorder at a specific pactl/pipewire source (mirrors
# recorder._DEVICE_FLAG; arecord uses ALSA names, so it stays on the default).
_DEVICE_FLAG: dict[str, list[str]] = {
    "pw-record": ["--target"],
    "parecord": ["-d"],
    "arecord": [],
}

_CHUNK_BYTES = 3200  # 100 ms of 16 kHz, 16-bit, mono → ~10 Hz level updates


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
    """Stream mic audio via a system recorder and call `on_level(0..1)` ~10x/s.

    Uses pw-record/parecord/arecord (the same recorders as the WAV recorder)
    rather than a Python audio binding, so it works on PipeWire boxes where
    PortAudio can't open the default input. Best-effort: ``start()`` returns
    False if no recorder is available or the device can't be opened.
    """

    def __init__(self, device: str = "", on_level=None, recorder: str = "auto"):
        self.device = device or ""
        self.on_level = on_level
        self._recorder = recorder
        self._proc: subprocess.Popen | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    def _argv(self, recorder: str) -> list[str]:
        argv = list(_METER_ARGV[recorder])
        flag = _DEVICE_FLAG.get(recorder, [])
        if self.device and flag:
            argv += flag + [self.device]
        return argv

    def start(self) -> bool:
        try:
            recorder = detect_recorder(self._recorder)
        except RuntimeError:
            return False
        if recorder not in _METER_ARGV:
            return False
        try:
            self._proc = subprocess.Popen(
                self._argv(recorder), stdout=subprocess.PIPE, stderr=subprocess.DEVNULL
            )
        except OSError:
            self._proc = None
            return False
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="LevelMeter")
        self._thread.start()
        return True

    def _loop(self) -> None:
        import numpy as np

        proc = self._proc
        if proc is None or proc.stdout is None:
            return
        try:
            while not self._stop.is_set() and proc.poll() is None:
                chunk = proc.stdout.read(_CHUNK_BYTES)
                if not chunk:
                    break
                samples = np.frombuffer(chunk, dtype=np.int16).astype(np.float32) / 32768.0
                level = float(np.sqrt(np.mean(np.square(samples)))) if samples.size else 0.0
                if self.on_level:
                    # Scale RMS (typically small) into a usable 0..1 range.
                    self.on_level(min(1.0, level * 12.0))
        except Exception:  # noqa: BLE001 - metering is eye-candy; never crash the app
            pass

    def stop(self) -> None:
        self._stop.set()
        proc, self._proc = self._proc, None
        if proc is not None and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=1.0)
            except subprocess.TimeoutExpired:
                proc.kill()
        thread, self._thread = self._thread, None
        if thread is not None:
            thread.join(timeout=1.0)
