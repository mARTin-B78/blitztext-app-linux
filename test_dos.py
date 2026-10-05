import threading
import time
import socket
import json

from linux.blitztext.wakeword import WakewordListener

def handle_detect(name):
    print("Detected", name)

listener = WakewordListener("localhost:10400", ["model"], "mic", handle_detect)

# Mock server
def server():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(("localhost", 10400))
        s.listen(1)
        conn, addr = s.accept()
        with conn:
            print("Connected by", addr)
            # wait a bit for listener to set up
            time.sleep(0.1)
            # send malicious length
            msg = {"type": "event", "data_length": 10**8}
            conn.sendall((json.dumps(msg) + "\n").encode("utf-8"))
            # then just send random bytes to keep it busy
            while True:
                conn.sendall(b"A" * 1024)
                time.sleep(0.01)

threading.Thread(target=server, daemon=True).start()

listener.start()
time.sleep(2)
listener.stop()
