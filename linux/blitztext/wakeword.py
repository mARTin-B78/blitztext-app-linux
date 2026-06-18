"""Wakeword detection using Wyoming protocol (openwakeword).

Runs a background thread that captures audio and streams it to a Wyoming 
server (e.g. rhasspy/wyoming-openwakeword). When a detection event occurs, 
it triggers the main daemon.

Respects /tmp/wake_muted to allow easy desktop integration via scripts.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import threading
import time
from urllib.parse import urlparse

from . import logbuffer

MUTE_FILE = "/tmp/wake_muted"


def is_muted() -> bool:
    """True if wakeword detections are currently paused via the mute flag."""
    return os.path.exists(MUTE_FILE)


def set_muted(muted: bool) -> None:
    """Pause (create flag) or resume (remove flag) wakeword detection."""
    try:
        if muted:
            open(MUTE_FILE, "a").close()
        elif os.path.exists(MUTE_FILE):
            os.remove(MUTE_FILE)
    except OSError as e:  # noqa: BLE001 - mute is best-effort, never crash
        logbuffer.log(f"[wakeword] Could not update mute flag: {e}", level="WARNING")


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
        parsed = urlparse(self.uri)
        host = parsed.hostname or "127.0.0.1"
        port = parsed.port or 10400

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(5.0)
            sock.connect((host, port))
            logbuffer.log(f"[wakeword] Connected to {self.uri}")
            
            # Request detection for all configured models
            detect_msg = {"type": "detect", "data": {"names": self.models}}
            sock.sendall((json.dumps(detect_msg) + "\n").encode("utf-8"))

            audio_start = {"type": "audio-start", "data": {"rate": 16000, "width": 2, "channels": 1}}
            sock.sendall((json.dumps(audio_start) + "\n").encode("utf-8"))

            # Start reading thread
            read_active = True
            
            def read_loop():
                try:
                    sock.settimeout(1.0)
                    while read_active and not self._stop_event.is_set():
                        try:
                            # Read line
                            line = b""
                            while not line.endswith(b"\n"):
                                byte = sock.recv(1)
                                if not byte:
                                    break
                                line += byte
                            
                            if not line:
                                break

                            msg = json.loads(line.decode("utf-8"))
                            
                            if msg.get("type") == "detection":
                                name = msg.get("data", {}).get("name", "")
                                self._handle_detection(name)

                            payload_len = msg.get("payload_length", 0)
                            if not (0 <= payload_len <= 10 * 1024 * 1024):
                                logbuffer.log(f"[wakeword] Disconnecting: payload length {payload_len} out of bounds", level="WARNING")
                                break
                            if payload_len > 0:
                                # Consume payload
                                remaining = payload_len
                                while remaining > 0:
                                    received = sock.recv(min(remaining, 4096))
                                    if not received:
                                        break
                                    remaining -= len(received)
                        except socket.timeout:
                            pass
                except Exception:
                    pass
            
            reader_thread = threading.Thread(target=read_loop, daemon=True)
            reader_thread.start()

            # Start recording subprocess (16kHz, 16-bit, mono)
            cmd = ["pw-record", "--rate=16000", "--channels=1", "--format=s16", "-"]
            if self.mic:
                cmd.extend(["--target", self.mic])
            
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            
            try:
                while not self._stop_event.is_set() and proc.poll() is None:
                    # Read chunk
                    chunk = proc.stdout.read(3200) # 100ms of 16kHz 16-bit mono
                    if not chunk:
                        break
                    
                    # Send chunk
                    header = {"type": "audio-chunk", "data": {"rate": 16000, "width": 2, "channels": 1}, "payload_length": len(chunk)}
                    sock.sendall((json.dumps(header) + "\n").encode("utf-8"))
                    sock.sendall(chunk)
            finally:
                read_active = False
                proc.terminate()
                try:
                    proc.wait(timeout=1.0)
                except subprocess.TimeoutExpired:
                    proc.kill()
                reader_thread.join(timeout=1.0)

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

    def __init__(self, uri: str, model_callbacks: dict, mic: str):
        self.uri = uri
        self.model_callbacks = dict(model_callbacks)   # {name: callable}
        self.mic = mic
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if not self.model_callbacks:
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run, daemon=True, name="WakewordActionListener")
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
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
        parsed = urlparse(self.uri)
        host = parsed.hostname or "127.0.0.1"
        port = parsed.port or 10400

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(5.0)
            sock.connect((host, port))
            logbuffer.log(f"[wakeword-action] Connected — listening for {list(self.model_callbacks)}")

            detect_msg = {"type": "detect", "data": {"names": list(self.model_callbacks)}}
            sock.sendall((json.dumps(detect_msg) + "\n").encode("utf-8"))

            audio_start = {"type": "audio-start",
                           "data": {"rate": 16000, "width": 2, "channels": 1}}
            sock.sendall((json.dumps(audio_start) + "\n").encode("utf-8"))

            read_active = True

            def read_loop() -> None:
                try:
                    sock.settimeout(1.0)
                    while read_active and not self._stop_event.is_set():
                        try:
                            line = b""
                            while not line.endswith(b"\n"):
                                byte = sock.recv(1)
                                if not byte:
                                    return
                                line += byte
                            if not line:
                                return
                            msg = json.loads(line.decode("utf-8"))
                            if msg.get("type") == "detection":
                                name = msg.get("data", {}).get("name", "")
                                cb = self.model_callbacks.get(name)
                                if cb is None:
                                    # Try partial match — some servers omit the lang suffix
                                    for k, v in self.model_callbacks.items():
                                        if name.startswith(k) or k.startswith(name):
                                            cb = v
                                            break
                                if cb:
                                    logbuffer.log(
                                        f"[wakeword-action] '{name}' detected — firing action")
                                    self._stop_event.set()   # one-shot: stop after first fire
                                    cb()
                            payload_len = msg.get("payload_length", 0)
                            if not (0 <= payload_len <= 10 * 1024 * 1024):
                                logbuffer.log(f"[wakeword-action] Disconnecting: payload length {payload_len} out of bounds", level="WARNING")
                                break
                            if payload_len > 0:
                                remaining = payload_len
                                while remaining > 0:
                                    chunk = sock.recv(min(remaining, 4096))
                                    if not chunk:
                                        break
                                    remaining -= len(chunk)
                        except socket.timeout:
                            pass
                except Exception:
                    pass

            reader = threading.Thread(target=read_loop, daemon=True)
            reader.start()

            cmd = ["pw-record", "--rate=16000", "--channels=1", "--format=s16", "-"]
            if self.mic:
                cmd.extend(["--target", self.mic])
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)

            try:
                while not self._stop_event.is_set() and proc.poll() is None:
                    chunk = proc.stdout.read(3200)
                    if not chunk:
                        break
                    header = {"type": "audio-chunk",
                              "data": {"rate": 16000, "width": 2, "channels": 1},
                              "payload_length": len(chunk)}
                    sock.sendall((json.dumps(header) + "\n").encode("utf-8"))
                    sock.sendall(chunk)
            finally:
                read_active = False
                proc.terminate()
                try:
                    proc.wait(timeout=1.0)
                except subprocess.TimeoutExpired:
                    proc.kill()
                reader.join(timeout=1.0)
