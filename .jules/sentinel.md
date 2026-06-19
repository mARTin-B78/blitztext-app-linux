## 2024-06-13 — [Untrusted Parsing Bounds Check]
**Learning:** The Wyoming protocol wake-word listener logic reads network payload bytes dynamically based on the parsed JSON header. Without a boundary check, a malicious payload length could cause an unbounded read and a Denial of Service.
**Action:** Added a `MAX_PAYLOAD_BYTES` limit of 10MB to the socket receive logic in `wakeword.py` and `wakeword_bench.py`.
