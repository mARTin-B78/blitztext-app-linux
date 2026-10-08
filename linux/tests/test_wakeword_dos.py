import pytest
from blitztext.wakeword_bench import _drain_detections

def test_drain_detections_unbounded_payload():
    """Verify that _drain_detections raises ValueError on excessive payload lengths."""
    payload = b'{"type": "detection", "payload_length": 100000000}\n'
    with pytest.raises(ValueError, match="Payload length too large"):
        _drain_detections(payload)
