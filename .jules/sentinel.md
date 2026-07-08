## 2026-07-02 — [DoS via unbounded read in Wyoming protocol]
**Learning:** The Wyoming protocol network parsers in `wakeword.py` and `wakeword_bench.py` were missing length bounds on headers and payloads, making them vulnerable to unbounded memory allocation (DoS) if a server sends a stream lacking newline delimiters.
**Action:** Added hard limits: 64KB for JSON header strings and 1MB for binary data payloads. Refactored reading loops to raise ValueError upon exceeding limits.
