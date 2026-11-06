"""Characterization tests for the Wyoming streaming loops in wakeword.py.

A real localhost TCP server plays the Wyoming side; pw-record is faked.
"""

import json
import socket
import threading
import time
from unittest import mock

from blitztext import wakeword


def _event(sock, etype, data=None, payload=b"", inline=False):
    header = {"type": etype}
    blob = b""
    if data is not None:
        if inline:
            header["data"] = data
        else:
            blob = json.dumps(data).encode()
            header["data_length"] = len(blob)
    if payload:
        header["payload_length"] = len(payload)
    sock.sendall((json.dumps(header) + "\n").encode() + blob + payload)


class FakeServer:
    """Accepts one client, records its header lines, sends scripted events."""

    def __init__(self, script):
        self.srv = socket.socket()
        self.srv.bind(("127.0.0.1", 0))
        self.srv.listen(1)
        self.port = self.srv.getsockname()[1]
        self.script = script
        self.headers = []
        self.thread = threading.Thread(target=self._serve, daemon=True)
        self.thread.start()

    def _serve(self):
        conn, _ = self.srv.accept()
        with conn:
            f = conn.makefile("rb")
            # detect + audio-start come first
            for _ in range(2):
                self.headers.append(json.loads(f.readline()))
            self.script(conn)
            conn.settimeout(0.5)
            try:
                while True:
                    line = f.readline()
                    if not line:
                        break
                    hdr = json.loads(line)
                    self.headers.append(hdr)
                    f.read(hdr.get("payload_length", 0))
            except (OSError, ValueError):
                pass
        self.srv.close()

    @property
    def uri(self):
        return f"tcp://127.0.0.1:{self.port}"


class FakeProc:
    def __init__(self, chunks=10):
        self.left = chunks
        self.stdout = self
        self.terminated = False

    def read(self, n):
        time.sleep(0.05)
        if self.left <= 0:
            return b""
        self.left -= 1
        return b"\0" * n

    def poll(self):
        return None

    def terminate(self):
        self.terminated = True

    def wait(self, timeout=None):
        return 0


def test_listener_detects_with_data_block_and_payload(monkeypatch):
    monkeypatch.setattr(wakeword, "is_muted", lambda: False)

    def script(conn):
        _event(conn, "info", payload=b"x" * 5000)  # payload must be skipped
        _event(conn, "detection", {"name": "hey_jarvis"})

    srv = FakeServer(script)
    hits = []
    lst = wakeword.WakewordListener(srv.uri, ["hey_jarvis", ""], "mymic", lambda: hits.append(1))
    proc = FakeProc()
    with mock.patch.object(wakeword.subprocess, "Popen", return_value=proc) as popen:
        lst._stream()
    assert hits == [1]
    assert proc.terminated
    cmd = popen.call_args[0][0]
    assert cmd == ["pw-record", "--rate=16000", "--channels=1", "--format=s16", "-",
                   "--target", "mymic"]
    assert srv.headers[0] == {"type": "detect", "data": {"names": ["hey_jarvis"]}}
    assert srv.headers[1] == {"type": "audio-start",
                              "data": {"rate": 16000, "width": 2, "channels": 1}}
    chunks = [h for h in srv.headers[2:] if h["type"] == "audio-chunk"]
    assert chunks and chunks[0]["payload_length"] == 3200


def test_listener_cooldown_and_mute(monkeypatch):
    hits = []
    lst = wakeword.WakewordListener("tcp://x:1", ["m"], "", lambda: hits.append(1))
    monkeypatch.setattr(wakeword, "is_muted", lambda: True)
    lst._handle_detection("m")
    assert hits == []
    monkeypatch.setattr(wakeword, "is_muted", lambda: False)
    lst._handle_detection("m")
    lst._handle_detection("m")  # within cooldown
    assert hits == [1]


def _action(srv, callbacks, external=True):
    lst = wakeword.WakewordActionListener(srv.uri, callbacks, "", external_audio=external)
    t = threading.Thread(target=lst._stream, daemon=True)
    t.start()
    return lst, t


def test_action_exact_and_partial_match_external_audio():
    def script(conn):
        _event(conn, "detection", {})                       # nameless: ignored
        _event(conn, "detection", {"name": "unknown"})      # no match
        _event(conn, "detection", {"name": "send_de"}, payload=b"y" * 10)

    srv = FakeServer(script)
    fired = []
    lst, t = _action(srv, {"cancel": lambda: fired.append("c"),
                           "send": lambda: fired.append("s")})
    lst.feed(b"\1" * 320)
    t.join(timeout=5)
    assert not t.is_alive()
    assert fired == ["s"]
    assert lst._stop_event.is_set()
    srv.thread.join(timeout=3)
    chunks = [h for h in srv.headers if h["type"] == "audio-chunk"]
    assert chunks and chunks[0]["payload_length"] == 320
    assert srv.headers[0]["data"]["names"] == ["cancel", "send"]


def test_action_inline_data_exact_match():
    def script(conn):
        _event(conn, "detection", {"name": "cancel"}, inline=True)

    srv = FakeServer(script)
    fired = []
    lst, t = _action(srv, {"cancel": lambda: fired.append("c")})
    t.join(timeout=5)
    assert fired == ["c"]


def test_action_feed_none_stops_external_loop():
    srv = FakeServer(lambda conn: None)
    lst, t = _action(srv, {"cancel": lambda: None})
    time.sleep(0.2)
    lst._audio_q.put(None)
    t.join(timeout=5)
    assert not t.is_alive()
    assert not lst._stop_event.is_set()


def test_action_mic_mode_uses_pw_record():
    def script(conn):
        _event(conn, "detection", {"name": "stop"})

    srv = FakeServer(script)
    fired = []
    proc = FakeProc(chunks=40)
    with mock.patch.object(wakeword.subprocess, "Popen", return_value=proc):
        lst, t = _action(srv, {"stop": lambda: fired.append(1)}, external=False)
        t.join(timeout=5)
    assert fired == [1]
    assert proc.terminated


def test_feed_ignored_without_external_audio():
    lst = wakeword.WakewordActionListener("tcp://x:1", {"a": print}, "")
    lst.feed(b"abc")
    assert lst._audio_q.empty()


def test_listener_rejects_huge_payload():
    def script(conn):
        conn.sendall(b'{"type": "info", "payload_length": 20000000}\n')

    srv = FakeServer(script)
    hits = []
    lst = wakeword.WakewordListener(srv.uri, ["hey"], "mymic", lambda: hits.append(1))
    proc = FakeProc()
    with mock.patch.object(wakeword.subprocess, "Popen", return_value=proc):
        lst._stream()
    assert hits == []
    assert proc.terminated
