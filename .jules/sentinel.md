
## 2024-05-19 — Added network limits for wakeword connections
**Learning:** The wakeword parser consumes input directly from a socket without verifying line or payload bounds, creating a potential vector for DoS via infinite strings or gigantic payload allocations.
**Action:** Enforced a 64KB max line length and 10MB `payload_length` limits in both `wakeword.py` and `wakeword_bench.py`.
