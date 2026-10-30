import json

import pytest

from blitztext import wakeword_bench as wb


def test_drain_detections_payload_length_bounds():
    det = (json.dumps({"type": "detection", "payload_length": 2000000}) + "\n").encode()
    with pytest.raises(ValueError, match="lengths out of bounds"):
        wb._drain_detections(det)
