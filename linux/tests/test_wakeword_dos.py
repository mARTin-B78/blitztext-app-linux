import json

import pytest

from blitztext.wakeword_bench import _drain_detections


def test_drain_detections_rejects_huge_payload():
    # A realistic size is fine
    chunk_ok = (json.dumps({"type": "audio-chunk", "payload_length": 3200}) + "\n").encode() + b"a" * 3200
    rest, n = _drain_detections(chunk_ok)
    assert n == 0

    # Unreasonably large size should raise ValueError
    chunk_bad = (json.dumps({"type": "audio-chunk", "payload_length": 1048577}) + "\n").encode() + b"a" * 10
    with pytest.raises(ValueError, match="payload_length too large"):
        _drain_detections(chunk_bad)
