## 2024-05-18 — Fix unbounded read vulnerability in Wyoming protocol parser
**Learning:** Network parsing loops must not trust user-controlled payload length fields. An attacker could specify an extremely large value to trigger unbounded reads, leading to memory exhaustion and DoS.
**Action:** Added explicit bounds checks (e.g., maximum 1MB) for `payload_length` and `data_length` in all Wyoming protocol parsing loops across `wakeword.py`, `wakeword_bench.py`, and `gtksettings.py`. Exceeding the bound explicitly raises a `ValueError` to break the parsing loop immediately.
