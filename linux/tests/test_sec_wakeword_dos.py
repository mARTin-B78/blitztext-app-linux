import pytest
import socket
import threading
import json
from blitztext import wakeword, wakeword_bench

def test_wakeword_data_len_dos():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    port = server.getsockname()[1]

    def _serve():
        conn, _ = server.accept()
        # Send a message with a huge data_length
        msg = {"type": "detect", "data_length": 2000000000}
        conn.sendall((json.dumps(msg) + "\n").encode("utf-8"))
        conn.close()

    t = threading.Thread(target=_serve, daemon=True)
    t.start()

    with pytest.raises(ValueError, match="too large") as exc:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(1.0)
            sock.connect(("127.0.0.1", port))
            line = wakeword._recv_line(sock)
            msg = json.loads(line.decode("utf-8"))
            wakeword._read_event_body(sock, msg)

    t.join(timeout=1.0)
    server.close()
