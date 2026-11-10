import json
import pytest

from blitztext import wakeword
from blitztext import wakeword_bench
from blitztext import gtksettings


class DummySock:
    def recv(self, n):
        return b"A" * min(n, 4096)

    def settimeout(self, *args):
        pass


def test_wakeword_read_event_body_bounds():
    sock = DummySock()

    msg = {"data_length": 1048577}
    with pytest.raises(ValueError, match="too large"):
        wakeword._read_event_body(sock, msg)

    msg2 = {"payload_length": 1048577}
    with pytest.raises(ValueError, match="too large"):
        wakeword._read_event_body(sock, msg2)

def test_wakeword_bench_drain_detections_bounds():
    buf = json.dumps({"type": "test", "payload_length": 1048577}).encode() + b"\n"
    with pytest.raises(ValueError, match="too large"):
        wakeword_bench._drain_detections(buf)

def test_gtksettings_wyoming_describe_bounds():
    def mock_create_connection(*args, **kwargs):
        class MockSock:
            def __init__(self):
                self.resp = json.dumps({"data_length": 1048577}).encode() + b"\n"
                self.pos = 0
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def sendall(self, *args): pass
            def recv(self, n):
                if self.pos < len(self.resp):
                    chunk = self.resp[self.pos:self.pos+n]
                    self.pos += n
                    return chunk
                return b"A" * min(n, 4096)
        return MockSock()

    import socket
    original = socket.create_connection
    socket.create_connection = mock_create_connection
    try:
        with pytest.raises(ValueError, match="too large"):
            gtksettings._wyoming_describe("localhost", 10400)
    finally:
        socket.create_connection = original
