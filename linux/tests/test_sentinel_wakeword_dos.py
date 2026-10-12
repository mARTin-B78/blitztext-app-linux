import pytest
from blitztext import wakeword_bench

def test_drain_detections_payload_length_dos():
    import json
    # A massive payload length should raise ValueError rather than blocking or returning early without error
    chunk = (json.dumps({"type": "audio-chunk", "payload_length": 20 * 1024 * 1024}) + "\n").encode()
    with pytest.raises(ValueError, match="payload_length too large"):
        wakeword_bench._drain_detections(chunk)
