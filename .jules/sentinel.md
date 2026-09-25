## 2024-11-20 — [Sentinel: Prevent DoS on unbounded socket read]
**Learning:** Unbounded network reads without length limits can lead to denial-of-service vulnerabilities. Discovering an out-of-bounds length must explicitly break the loop or raise an exception like ValueError, to drop the connection instead of just continuing.
**Action:** Added `ValueError` exceptions for `data_length` and `payload_length` greater than 1MB in the Wyoming client parsing loop (`wakeword.py` and `wakeword_bench.py`).
