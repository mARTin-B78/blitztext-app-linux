import json
from blitztext.wakeword_bench import _drain_detections

def test_drain_detections_oversized_payload_len():
    # Attempting to declare an oversized payload should gracefully abort
    # without trying to buffer gigabytes of memory.
    buf = json.dumps({"type": "detection", "payload_length": 10**8}).encode() + b"\n"
    buf += b"x" * 100
    rest, count = _drain_detections(buf)

    # We should return the original buffer untouched and a count of 0
    assert count == 0
    assert rest == buf

def test_drain_detections_negative_payload_len():
    # Attempting to declare a negative payload length
    buf = json.dumps({"type": "detection", "payload_length": -10}).encode() + b"\n"
    buf += b"x" * 100
    rest, count = _drain_detections(buf)

    assert count == 0
    assert rest == buf
