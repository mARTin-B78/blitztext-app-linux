## 2025-02-21 — Enforce network read bounds against DoS in Wyoming client
**Learning:** Parsing newline-framed JSON and binary payloads from untrusted network servers without explicit read limits allows denial-of-service via unbounded memory allocation (if delimiters are omitted) or arbitrary payload lengths.
**Action:** Enforced a 64KB length check inside byte-by-byte header read loops and a 1MB limit on `data_length` and `payload_length` properties before consuming payloads in `wakeword.py` and `wakeword_bench.py`.
