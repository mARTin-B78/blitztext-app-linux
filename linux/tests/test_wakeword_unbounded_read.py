
import pytest

from blitztext.wakeword_bench import _drain_detections


def test_drain_detections_bounds():
    with pytest.raises(ValueError, match="Invalid payload length"):
        _drain_detections(b'{"payload_length": -1}\n{"type": "detection"}')

    with pytest.raises(ValueError, match="Invalid payload length"):
        _drain_detections(b'{"payload_length": 2000000}\n{"type": "detection"}')

    # Valid
    buf, found = _drain_detections(b'{"type": "detection", "payload_length": 5}\n12345{"type": "detection", "payload_length": 2}\n12')
    assert found == 2
    assert buf == b""
