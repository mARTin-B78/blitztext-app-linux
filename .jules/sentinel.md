## 2023-10-27 — Bound untrusted Wyoming lengths
**Learning:** Untrusted network responses with arbitrary `payload_length` or `data_length` can cause unbounded read loops (DoS) if left unchecked.
**Action:** Enforced a 10MB sanity limit on `payload_length` and `data_length` parsing loops in `wakeword.py`, `gtksettings.py`, and `wakeword_bench.py` to explicitly break the read connection by raising ValueError.
