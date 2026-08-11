## 2024-05-18 — Enforce payload size limits on wakeword server responses
**Learning:** Found an unbounded payload parsing vulnerability in the Wyoming stream handler `wakeword.py` where payload read bounds were never verified.
**Action:** Implemented strict 64 KB limit hard failures using returning thread closures for headers, `data_length`, and `payload_length` chunks avoiding arbitrary read loop DOS limits along with `wakeword_bench.py` bounds raising `ValueError`.
