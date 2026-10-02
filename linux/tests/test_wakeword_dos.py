import socket
import json
import threading
import pytest
from blitztext.wakeword import WakewordListener

def mock_server(host, port, large_length):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((host, port))
        s.listen(1)
        try:
            s.settimeout(2.0)
            conn, _ = s.accept()
            with conn:
                header = {"type": "test", "payload_length": large_length}
                conn.sendall((json.dumps(header) + "\n").encode("utf-8"))
        except Exception:
            pass

def test_wakeword_listener_bounds_check():
    port = 10406
    large_length = 20 * 1024 * 1024
    server_thread = threading.Thread(target=mock_server, args=("127.0.0.1", port, large_length))
    server_thread.start()

    listener = WakewordListener(uri=f"tcp://127.0.0.1:{port}", models=["test_model"], mic="test_mic", on_detect=lambda x: None)

    listener.start()
    # Sleep briefly to allow thread to start and hit the ValueError
    import time
    time.sleep(0.5)
    listener.stop()
    server_thread.join(timeout=2.0)
    assert not server_thread.is_alive()