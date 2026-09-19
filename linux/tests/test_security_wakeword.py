import pytest
import json
from blitztext.wakeword_bench import _drain_detections

def test_drain_detections_unbounded_payload():
    malicious_msg = {"type": "detection", "payload_length": 10485761}
    buf = (json.dumps(malicious_msg) + "\n").encode("utf-8")
    with pytest.raises(ValueError, match="too large"):
        _drain_detections(buf)
