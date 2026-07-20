import pytest
import json
from blitztext.wakeword_bench import _drain_detections

def test_drain_detections_bounds():
    # Test valid message passes
    valid_msg = json.dumps({"type": "detection", "payload_length": 5}).encode("utf-8") + b"\n" + b"12345"
    rest, found = _drain_detections(valid_msg)
    assert found == 1
    assert rest == b""

    # Test header line exceeding 64KB raises ValueError
    huge_header = b"x" * 65537 + b"\n"
    with pytest.raises(ValueError, match="Header line exceeds 64KB limit"):
        _drain_detections(huge_header)

    # Test buffer without newline exceeding 64KB raises ValueError
    huge_no_newline = b"x" * 65537
    with pytest.raises(ValueError, match="Header line exceeds 64KB limit"):
        _drain_detections(huge_no_newline)

    # Test payload length exceeding 1MB limit raises ValueError
    huge_payload_msg = json.dumps({"type": "detection", "payload_length": 1024 * 1024 + 1}).encode("utf-8") + b"\n"
    with pytest.raises(ValueError, match="Payload length exceeds 1MB limit"):
        _drain_detections(huge_payload_msg)
