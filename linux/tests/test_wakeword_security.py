import pytest
from blitztext.wakeword import _read_event_body
from blitztext.wakeword_bench import _drain_detections

def test_wakeword_unbounded_payload():
    with pytest.raises(ValueError, match="Payload length out of bounds"):
        _read_event_body(None, {"payload_length": 10485760 + 1})

    with pytest.raises(ValueError, match="Payload length out of bounds"):
        _read_event_body(None, {"data_length": -1})

    with pytest.raises(ValueError, match="Payload length out of bounds"):
        _read_event_body(None, {"data_length": 10485760 + 1})

def test_wakeword_bench_unbounded_payload():
    with pytest.raises(ValueError, match="Payload length out of bounds"):
        _drain_detections(b'{"payload_length": 10485761}\n')

    with pytest.raises(ValueError, match="Payload length out of bounds"):
        _drain_detections(b'{"payload_length": -1}\n')
