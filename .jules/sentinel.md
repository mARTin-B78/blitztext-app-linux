
## 2026-10-29 — [Prevent Wyoming unbounded read DoS]
 **Learning:** Wyoming protocol parsers must enforce size limits on network-derived lengths to prevent unbounded memory allocation or blocking DoS loops.
 **Action:** Added ValueError checks in blitztext/wakeword.py and blitztext/wakeword_bench.py when data_length or payload_length exceeds 1MB, ensuring the connection aborts instead of hanging.
