"""Wakeword detection using Wyoming protocol (openwakeword).

Runs a background thread that captures audio and streams it to a Wyoming 
server (e.g. rhasspy/wyoming-openwakeword). When a detection event occurs, 
it triggers the main daemon.

Respects a per-user mute flag file (see MUTE_FILE) to allow easy desktop
integration via scripts.
"""

from __future__ import annotations

import json
import os
import queue
import socket
import subprocess
import threading
import time
from urllib.parse import urlparse

from . import logbuffer

# Per-user location (XDG_RUNTIME_DIR is 0700 per user): a fixed /tmp name let
# any local user plant the flag (mute someone else's wakeword) or a symlink.
MUTE_FILE = os.path.join(
    os.environ.get("XDG_RUNTIME_DIR")
    or os.path.join(os.path.expanduser("~"), ".cache", "blitztext"),
    "blitztext-wake_muted",
)


def is_muted() -> bool:
    """True if wakeword detections are currently paused via the mute flag."""
    return os.path.exists(MUTE_FILE)


def set_muted(muted: bool) -> None:
    """Pause (create flag) or resume (remove flag) wakeword detection."""
    try:
        if muted:
            os.makedirs(os.path.dirname(MUTE_FILE), mode=0o700, exist_ok=True)
            open(MUTE_FILE, "a").close()
        elif os.path.exists(MUTE_FILE):
            os.remove(MUTE_FILE)
    except OSError as e:  # noqa: BLE001 - mute is best-effort, never crash
        logbuffer.log(f"[wakeword] Could not update mute flag: {e}", level="WARNING")


_AUDIO_FORMAT = {"rate": 16000, "width": 2, "channels": 1}


def _send_json(sock, obj) -> None:
    sock.sendall((json.dumps(obj) + "\n").encode("utf-8"))


def _connect(sock, uri: str) -> None:
    parsed = urlparse(uri)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or 10400
    sock.settimeout(5.0)
    sock.connect((host, port))


def _send_start(sock, names: list) -> None:
    _send_json(sock, {"type": "detect", "data": {"names": names}})
    _send_json(sock, {"type": "audio-start", "data": dict(_AUDIO_FORMAT)})


def _send_chunk(sock, chunk: bytes) -> None:
    _send_json(sock, {"type": "audio-chunk", "data": dict(_AUDIO_FORMAT),
                      "payload_length": len(chunk)})
    sock.sendall(chunk)


def _recv_line(sock) -> bytes:
    """Read one header line byte-wise; a result without trailing newline means EOF."""
    line = b""
    while not line.endswith(b"\n"):
        byte = sock.recv(1)
        if not byte:
            break
        line += byte
    return line


def _read_event_body(sock, msg: dict) -> None:
    """Read the event's separate ``data`` block and skip its payload.

    Wyoming sends the event's `data` as a separate `data_length` block after the
    header line (not inline) — newer servers like wyoming-microwakeword always
    do. Read it so the wake-word name is available and the stream stays in sync.
    """
    data_len = msg.get("data_length") or 0
    if data_len < 0 or data_len > 10485760:
        raise ValueError(f"Unbounded data_length: {data_len}")
    if data_len > 0:
        data_bytes = b""
        while len(data_bytes) < data_len:
            r = sock.recv(min(data_len - len(data_bytes), 4096))
            if not r:
                break
            data_bytes += r
        try:
            msg["data"] = json.loads(data_bytes.decode("utf-8"))
        except Exception:
            pass

    remaining = msg.get("payload_length") or 0
    if remaining < 0 or remaining > 10485760:
        raise ValueError(f"Unbounded payload_length: {remaining}")
    while remaining > 0:
        received = sock.recv(min(remaining, 4096))
        if not received:
            break
        remaining -= len(received)


def _pw_record_cmd(mic: str) -> list[str]:
    """Recording subprocess command (16kHz, 16-bit, mono)."""
    cmd = ["pw-record", "--rate=16000", "--channels=1", "--format=s16", "-"]
    if mic:
        cmd.extend(["--target", mic])
    return cmd


def _pump_mic(proc, stop_event, sock) -> None:
    while not stop_event.is_set() and proc.poll() is None:
        chunk = proc.stdout.read(3200)  # 100ms of 16kHz 16-bit mono
        if not chunk:
            break
        _send_chunk(sock, chunk)


def _stop_proc(proc) -> None:
    proc.terminate()
    try:
        proc.wait(timeout=1.0)
    except subprocess.TimeoutExpired:
        proc.kill()


class WakewordListener:
    def __init__(self, uri: str, models: list[str], mic: str, on_detect):
        self.uri = uri
        self.models = [m for m in models if m]
        self.mic = mic
        self.on_detect = on_detect
        
        self._stop_event = threading.Event()
        self._thread = None
        self._cooldown_until = 0.0

    def start(self):
        if self._thread is not None:
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="WakewordListener")
        self._thread.start()

    def stop(self):
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=2.0)
            self._thread = None

    def _run(self):
        while not self._stop_event.is_set():
            try:
                self._stream()
            except Exception as e:
                logbuffer.log(f"[wakeword] Connection error: {e}", level="WARNING")
                time.sleep(3)  # Retry backoff

    def _stream(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            _connect(sock, self.uri)
            logbuffer.log(f"[wakeword] Connected to {self.uri}")

            # Request detection for all configured models
            _send_start(sock, self.models)

            # Start reading thread
            read_active = True
            reader_thread = threading.Thread(
                target=self._read_loop, args=(sock, lambda: read_active), daemon=True)
            reader_thread.start()

            proc = subprocess.Popen(_pw_record_cmd(self.mic),
                                    stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            try:
                _pump_mic(proc, self._stop_event, sock)
            finally:
                read_active = False
                _stop_proc(proc)
                reader_thread.join(timeout=1.0)

    def _read_loop(self, sock, is_active) -> None:
        try:
            sock.settimeout(1.0)
            while is_active() and not self._stop_event.is_set():
                try:
                    line = _recv_line(sock)
                    if not line:
                        break
                    msg = json.loads(line.decode("utf-8"))
                    _read_event_body(sock, msg)
                    if msg.get("type") == "detection":
                        self._handle_detection(msg.get("data", {}).get("name", ""))
                except socket.timeout:
                    pass
        except Exception:
            pass

    def _handle_detection(self, name: str = ""):
        if time.time() < self._cooldown_until:
            return

        if is_muted():
            logbuffer.log("[wakeword] Detected, but paused (resume via tray)")
            return

        logbuffer.log(f"[wakeword] Detected '{name or self.models}'!")
        self._cooldown_until = time.time() + 3.0  # 3s cooldown
        self.on_detect()


class WakewordActionListener:
    """Listens for multiple wakeword models simultaneously and calls per-model callbacks.

    Used during active wakeword recording so that dedicated "cancel" and "send"
    wakeword phrases trigger :meth:`~blitztext.daemon.Daemon.cancel_dictation` or
    :meth:`~blitztext.daemon.Daemon.finish_dictation` immediately — much faster
    than waiting for Whisper to transcribe the whole clip.

    ``model_callbacks`` is a ``{model_name: callable}`` dict; only the models
    present in the dict are requested from the server.  No cooldown is applied
    because the listener is torn down immediately after the first action fires.
    """

    def __init__(self, uri: str, model_callbacks: dict, mic: str,
                 external_audio: bool = False):
        self.uri = uri
        self.model_callbacks = dict(model_callbacks)   # {name: callable}
        self.mic = mic
        # When ``external_audio`` is set the listener does NOT open its own mic;
        # the daemon feeds it the same PCM the recorder already captured (via
        # ``feed``). Avoids a second/competing ``pw-record`` on the same device,
        # which made real-time cancel/send/stop detection flaky during recording.
        self.external_audio = external_audio
        self._audio_q: "queue.Queue[bytes | None]" = queue.Queue()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def feed(self, chunk: bytes) -> None:
        """Supply a chunk of 16 kHz s16le mono PCM (external-audio mode)."""
        if self.external_audio and not self._stop_event.is_set():
            self._audio_q.put(chunk)

    def start(self) -> None:
        if not self.model_callbacks:
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run, daemon=True, name="WakewordActionListener")
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        self._audio_q.put(None)   # unblock the fed-audio loop immediately
        if self._thread:
            self._thread.join(timeout=2.0)
            self._thread = None

    def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                self._stream()
            except Exception as e:
                logbuffer.log(f"[wakeword-action] Connection error: {e}", level="WARNING")
                time.sleep(2)

    def _stream(self) -> None:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            _connect(sock, self.uri)
            logbuffer.log(f"[wakeword-action] Connected — listening for {list(self.model_callbacks)}")
            _send_start(sock, list(self.model_callbacks))

            read_active = True
            reader = threading.Thread(
                target=self._read_loop, args=(sock, lambda: read_active), daemon=True)
            reader.start()

            if self.external_audio:
                # Audio is fed in via feed() from the shared recorder capture —
                # no own pw-record, so no contention on the mic device.
                try:
                    self._pump_fed_audio(sock)
                finally:
                    read_active = False
                    reader.join(timeout=1.0)
                return

            proc = subprocess.Popen(_pw_record_cmd(self.mic),
                                    stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            try:
                _pump_mic(proc, self._stop_event, sock)
            finally:
                read_active = False
                _stop_proc(proc)
                reader.join(timeout=1.0)

    def _pump_fed_audio(self, sock) -> None:
        while not self._stop_event.is_set():
            try:
                chunk = self._audio_q.get(timeout=0.2)
            except queue.Empty:
                continue
            if chunk is None:
                break
            _send_chunk(sock, chunk)

    def _read_loop(self, sock, is_active) -> None:
        try:
            sock.settimeout(1.0)
            while is_active() and not self._stop_event.is_set():
                try:
                    line = _recv_line(sock)
                    if not line.endswith(b"\n"):
                        return  # EOF
                    msg = json.loads(line.decode("utf-8"))
                    # Read the separate `data` block — without it the detection
                    # name is blank, so the wrong action (or none) fires.
                    _read_event_body(sock, msg)
                    if msg.get("type") == "detection":
                        self._on_detection(msg.get("data", {}).get("name", ""))
                except socket.timeout:
                    pass
        except Exception:
            pass

    def _match_callback(self, name: str):
        cb = self.model_callbacks.get(name)
        if cb is None:
            # Partial match — some servers add/omit a lang
            # suffix. Guard against empty name matching all.
            for k, v in self.model_callbacks.items():
                if k and (name.startswith(k) or k.startswith(name)):
                    return v
        return cb

    def _on_detection(self, name: str) -> None:
        if not name:
            return  # ignore nameless detections
        cb = self._match_callback(name)
        if cb:
            logbuffer.log(f"[wakeword-action] '{name}' detected — firing action")
            self._stop_event.set()   # one-shot: stop after first fire
            cb()
