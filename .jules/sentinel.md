## 2025-02-14 — Bound wakeword payload length
**Learning:** `payload_length` read from network JSON payloads in `wakeword.py` and `wakeword_bench.py` lacked bounds checks, allowing a malicious Wyoming server (or MITM) to cause a DoS by providing a huge length and freezing the read loop or consuming all memory.
**Action:** Added `if not (0 <= payload_len <= 10 * 1024 * 1024):` bounds check to safely drop oversized or negative `payload_length` frames.
