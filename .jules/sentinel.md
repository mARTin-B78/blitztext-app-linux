## 2024-05-19 — Bounds checking on Wyoming protocol network lengths
 **Learning:** Network streams processing JSON payloads must explicitly check requested string and payload lengths to prevent Denial of Service via unbounded reads.
 **Action:** Enforced 1MB max limits on `data_length` and `payload_length` values parsed from untrusted network sockets in `wakeword.py` and `wakeword_bench.py`.
