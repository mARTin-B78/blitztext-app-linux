import pytest
from blitztext.wakeword_bench import _drain_detections

def test_drain_detections_bounds():
    import json
    msg = {"type": "detection", "payload_length": 2000000}
    payload = json.dumps(msg).encode("utf-8") + b"\n"
    with pytest.raises(ValueError, match="Length exceeds 1MB bounds"):
        _drain_detections(payload)
