import json

def _drain_detections(buf: bytes):
    found = 0
    while b"\n" in buf:
        line, rest = buf.split(b"\n", 1)
        try:
            msg = json.loads(line.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return rest, found
        plen = msg.get("payload_length", 0) or 0
        if plen > 10 * 1024 * 1024:
            raise ValueError("Payload length exceeds maximum allowed size")
        if len(rest) < plen:
            return buf, found
        rest = rest[plen:]
        if msg.get("type") == "detection":
            found += 1
        buf = rest
    return buf, found
