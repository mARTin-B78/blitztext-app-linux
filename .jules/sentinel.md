## 2026-09-21 — Prevented unbounded read/DoS in wakeword parser
 **Learning:** Untrusted `payload_length` and `data_length` in Wyoming protocol parser could trigger unbounded reads/memory exhaustion.
 **Action:** Added bounds checking to `payload_length` and `data_length` in `wakeword.py` and `wakeword_bench.py` to raise `ValueError` and drop connection on excessive sizes.
