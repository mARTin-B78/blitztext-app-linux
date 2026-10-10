import json

import pytest

from blitztext.wakeword_bench import _drain_detections


def test_drain_detections_dos():
    msg = {"type": "detection", "payload_length": 15 * 1024 * 1024}
    buf = (json.dumps(msg) + "\n").encode("utf-8")
    with pytest.raises(ValueError, match="exceeds maximum allowed size"):
        _drain_detections(buf)
