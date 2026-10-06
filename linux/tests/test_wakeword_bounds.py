import json

import pytest

from blitztext.wakeword_bench import _drain_detections


def test_drain_detections_bounds():
    header = json.dumps({"type": "detect", "payload_length": 1048577}) + "\n"
    buf = header.encode("utf-8") + b"data"

    with pytest.raises(ValueError, match="Payload length too large"):
        _drain_detections(buf)
