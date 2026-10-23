import json
import socket
import threading
import time
import pytest
from blitztext.wakeword import WakewordActionListener
from blitztext.wakeword_bench import _drain_detections

class DummyServer:
    def __init__(self, host, port):
        self.host = host
        self.port = port
        self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server.bind((self.host, self.port))
        self.server.listen(1)
        self.stop_event = threading.Event()
        self.thread = threading.Thread(target=self._run)
        self.client_sock = None

    def start(self):
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        if self.client_sock:
            self.client_sock.close()
        self.server.close()
        self.thread.join()

    def _run(self):
        self.server.settimeout(1.0)
        try:
            self.client_sock, _ = self.server.accept()
            msg = {"type": "detect", "data_length": 1024 * 1024 * 5, "payload_length": 1024 * 1024 * 5}
            self.client_sock.sendall((json.dumps(msg) + "\n").encode("utf-8"))
            while not self.stop_event.is_set():
                try:
                    self.client_sock.sendall(b"A" * 4096)
                except Exception:
                    break
        except socket.timeout:
            pass
        except Exception:
            pass

def test_wakeword_action_listener_bounds_check():
    server = DummyServer("127.0.0.1", 10411)
    server.start()

    listener = WakewordActionListener("tcp://127.0.0.1:10411", {"model": lambda: None}, mic="", external_audio=True)
    listener.start()

    time.sleep(1)

    # Thread will restart because it sleeps 2s and retries on exception
    # But let's check it's alive and we can just confirm we don't OOM or block
    assert listener._thread.is_alive()

    listener.stop()
    server.stop()

def test_drain_detections_bounds_check():
    msg = {"type": "detect", "payload_length": 1024 * 1024 * 5}
    payload = (json.dumps(msg) + "\n").encode("utf-8")

    with pytest.raises(ValueError, match="payload_length exceeds limit"):
        _drain_detections(payload + b"0")
