import pytest
from blitztext import wakeword, wakeword_bench

def test_read_event_body_payload_length_bounds():
    class DummySock:
        def recv(self, n): return b"a" * n
    sock = DummySock()
    with pytest.raises(ValueError, match="data_length .* out of bounds"):
        wakeword._read_event_body(sock, {"data_length": -1})
    with pytest.raises(ValueError, match="data_length .* out of bounds"):
        wakeword._read_event_body(sock, {"data_length": 1048577})
    with pytest.raises(ValueError, match="payload_length .* out of bounds"):
        wakeword._read_event_body(sock, {"payload_length": -1})
    with pytest.raises(ValueError, match="payload_length .* out of bounds"):
        wakeword._read_event_body(sock, {"payload_length": 1048577})

def test_drain_detections_payload_length_bounds():
    with pytest.raises(ValueError, match="payload_length .* out of bounds"):
        wakeword_bench._drain_detections(b'{"type": "detection", "payload_length": 1048577}\n')
    with pytest.raises(ValueError, match="payload_length .* out of bounds"):
        wakeword_bench._drain_detections(b'{"type": "detection", "payload_length": -1}\n')
