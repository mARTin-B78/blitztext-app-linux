from blitztext.wakeword_bench import _drain_detections
import json

def test_drain_detections_normal():
    buf = json.dumps({"type": "detection", "payload_length": 5}).encode() + b"\n" + b"12345"
    rest, found = _drain_detections(buf)
    assert rest == b""
    assert found == 1

def test_drain_detections_large_payload():
    buf = json.dumps({"type": "detection", "payload_length": 1024 * 1024 * 1024}).encode() + b"\n" + b"wait"
    rest, found = _drain_detections(buf)
    assert rest == b""
    assert found == 0

def test_drain_detections_negative_payload():
    buf = json.dumps({"type": "detection", "payload_length": -1}).encode() + b"\n" + b"wait"
    rest, found = _drain_detections(buf)
    assert rest == b""
    assert found == 0

def test_drain_detections_non_int_payload():
    buf = json.dumps({"type": "detection", "payload_length": "abc"}).encode() + b"\n" + b"wait"
    rest, found = _drain_detections(buf)
    assert rest == b""
    assert found == 0
