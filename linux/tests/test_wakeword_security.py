import pytest
import json
from blitztext.wakeword_bench import _drain_detections

def test_wakeword_dos_payload_length():
    buf = b""
    msg = {"type": "detect", "payload_length": 10**8}
    buf += (json.dumps(msg) + "\n").encode("utf-8")

    with pytest.raises(ValueError):
        _drain_detections(buf)
