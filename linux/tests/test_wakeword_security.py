import pytest
from blitztext import wakeword
from blitztext import wakeword_bench

class FakeSocket:
    def __init__(self, data=b""):
        self.data = data
        self.recv_called = False

    def recv(self, size):
        self.recv_called = True
        return b""

def test_read_event_body_length_limits():
    # Valid limits should pass
    sock = FakeSocket()
    wakeword._read_event_body(sock, {"data_length": 1000, "payload_length": 1000})

    # Exceeding limits should raise ValueError
    with pytest.raises(ValueError):
        wakeword._read_event_body(sock, {"data_length": 2000000})

    with pytest.raises(ValueError):
        wakeword._read_event_body(sock, {"payload_length": 2000000})

    # Negative limits should raise ValueError
    with pytest.raises(ValueError):
        wakeword._read_event_body(sock, {"data_length": -1})

    with pytest.raises(ValueError):
        wakeword._read_event_body(sock, {"payload_length": -1})

def test_drain_detections_length_limits():
    # Valid limits should pass
    chunk = b'{"type": "audio-chunk", "payload_length": 3}\nabc'
    wakeword_bench._drain_detections(chunk)

    # Exceeding limits should raise ValueError
    chunk_huge = b'{"type": "audio-chunk", "payload_length": 2000000}\n'
    with pytest.raises(ValueError):
        wakeword_bench._drain_detections(chunk_huge)

    # Negative limits should raise ValueError
    chunk_neg = b'{"type": "audio-chunk", "payload_length": -1}\n'
    with pytest.raises(ValueError):
        wakeword_bench._drain_detections(chunk_neg)
