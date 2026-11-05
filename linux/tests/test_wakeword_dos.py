import json
import pytest
from unittest.mock import Mock
from blitztext.wakeword import _read_event_body
from blitztext.wakeword_bench import _drain_detections

def test_wakeword_dos_data_length():
    sock = Mock()
    msg = {"data_length": 20 * 1024 * 1024}
    with pytest.raises(ValueError, match="Data payload too large"):
        _read_event_body(sock, msg)

def test_wakeword_dos_payload_length():
    sock = Mock()
    msg = {"payload_length": 20 * 1024 * 1024}
    with pytest.raises(ValueError, match="Payload too large"):
        _read_event_body(sock, msg)

def test_wakeword_bench_dos_payload_length():
    buf = (json.dumps({"payload_length": 20 * 1024 * 1024}) + "\n").encode("utf-8")
    with pytest.raises(ValueError, match="Payload too large"):
        _drain_detections(buf)
