import json
import pytest

from blitztext.wakeword_bench import _drain_detections

def test_drain_detections_payload_length_validation():
    # Test massive payload length
    msg = {"type": "info", "payload_length": 1048577}
    buf = json.dumps(msg).encode("utf-8") + b"\n"
    with pytest.raises(ValueError, match="Unreasonably large payload_length"):
        _drain_detections(buf)

    # Test negative payload length
    msg = {"type": "info", "payload_length": -1}
    buf = json.dumps(msg).encode("utf-8") + b"\n"
    with pytest.raises(ValueError, match="Negative payload_length"):
        _drain_detections(buf)

    # Test invalid type for payload length
    msg = {"type": "info", "payload_length": "invalid"}
    buf = json.dumps(msg).encode("utf-8") + b"\n"
    with pytest.raises(ValueError, match="Invalid payload_length type"):
        _drain_detections(buf)
