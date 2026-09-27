## 2026-09-27 — [Bound payload_length in wakeword parsers]
 **Learning:** Unbounded payload length can cause DoS or hang connection in network protocol parsers like Wyoming.
 **Action:** Explicitly capped `payload_length` to 10MB to break loops on malicious size declarations.
