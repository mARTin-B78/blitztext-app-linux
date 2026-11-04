import pytest
from blitztext import wakeword, wakeword_bench, gtksettings

def test_wakeword_bench_drain_detections_bounds():
    with pytest.raises(ValueError):
        wakeword_bench._drain_detections(b'{"payload_length": 10000000}\n')

    with pytest.raises(ValueError):
        wakeword_bench._drain_detections(b'{"payload_length": -1}\n')

def test_wakeword_read_event_body_bounds():
    import socket
    sock = socket.socket()
    with pytest.raises(ValueError):
        wakeword._read_event_body(sock, {"payload_length": 10000000})

    with pytest.raises(ValueError):
        wakeword._read_event_body(sock, {"data_length": 10000000})
