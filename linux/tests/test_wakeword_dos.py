import pytest
import socket
import threading
import json
from blitztext.wakeword import WakewordListener
from blitztext.wakeword_bench import _drain_detections

def test_wakeword_listener_bounds_header():
    listener = WakewordListener("tcp://127.0.0.1:10401", "my_model", lambda: None, "")

    server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_sock.bind(("127.0.0.1", 10401))
    server_sock.listen(1)

    def server_thread():
        conn, addr = server_sock.accept()
        # Receive the request detection and audio start
        conn.recv(4096)
        conn.recv(4096)

        # Send an oversized header
        oversized = b"{\"type\": \"detect\"" + b" " * 70000 + b"}\n"
        conn.sendall(oversized)

        # In actual implementation the connection will be reset/closed
        try:
            conn.recv(4096)
        except Exception as e:
            _ = e
        conn.close()
        server_sock.close()

    t = threading.Thread(target=server_thread)
    t.start()

    # We will trigger the read_loop logic
    listener.start()
    t.join()
    listener.stop()

    # Wait for everything to shut down safely
    pass

def test_wakeword_listener_bounds_payload():
    listener = WakewordListener("tcp://127.0.0.1:10402", "my_model", lambda: None, "")

    server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_sock.bind(("127.0.0.1", 10402))
    server_sock.listen(1)

    def server_thread():
        conn, addr = server_sock.accept()
        # Receive the request detection and audio start
        conn.recv(4096)
        conn.recv(4096)

        # Send oversized payload length
        bad_payload = json.dumps({"type": "detect", "payload_length": 2000000}).encode() + b"\n"
        conn.sendall(bad_payload)

        try:
            conn.recv(4096)
        except Exception as e:
            _ = e
        conn.close()
        server_sock.close()

    t = threading.Thread(target=server_thread)
    t.start()

    # We will trigger the read_loop logic
    listener.start()
    t.join()
    listener.stop()

def test_drain_detections_bounds():
    with pytest.raises(ValueError, match="Header too large"):
        _drain_detections(b"{\"type\": \"detect\"" + b" " * 70000 + b"}\n")

    with pytest.raises(ValueError, match="Payload too large"):
        _drain_detections(b"{\"type\": \"detect\", \"payload_length\": 2000000}\n")
