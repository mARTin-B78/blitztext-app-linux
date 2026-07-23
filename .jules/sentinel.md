## $(date -I) — Enforce limits on Wyoming protocol parsing
**Learning:** Wyoming protocol network streams read unbounded lengths via `line = sock.recv(...)` while searching for `\n` in `wakeword.py` and `wakeword_bench.py`. If a malicious server omits newlines or sends extremely large `payload_length` values, this causes unbounded memory allocations and DoS.
**Action:** Enforced a 64KB limit on newline-separated header lines and a 1MB limit on `data_length` and `payload_length` parsed from JSON headers across all socket stream implementations.
