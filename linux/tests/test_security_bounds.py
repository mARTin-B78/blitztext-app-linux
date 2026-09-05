import pytest
import threading
import socket
import time
from unittest.mock import MagicMock
from blitztext.wakeword import WakewordListener
from blitztext.wakeword_bench import _drain_detections

def test_wakeword_bench_drain_detections_bounds():
    # Payload limit
    long_payload_header = b'{"payload_length": 1048577}\n'
    buf, found = _drain_detections(long_payload_header + b"x" * 10)
    assert buf == b""
    assert found == 0

    # Header limit
    long_header = b'{"type": "detect", "data": {"names": ["' + b"x" * 65536 + b'"]}}\n'
    buf, found = _drain_detections(long_header)
    assert buf == b""
    assert found == 0

    # Missing delimiter bound check
    long_no_newline = b"x" * 65537
    buf, found = _drain_detections(long_no_newline)
    assert buf == b""
    assert found == 0
