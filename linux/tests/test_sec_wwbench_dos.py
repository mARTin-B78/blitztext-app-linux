import pytest
import json
from blitztext import wakeword_bench

def test_wwbench_data_len_dos():
    msg = {"type": "detect", "payload_length": 2000000000}
    buf = (json.dumps(msg) + "\n").encode("utf-8")

    with pytest.raises(ValueError, match="too large"):
        wakeword_bench._drain_detections(buf)
