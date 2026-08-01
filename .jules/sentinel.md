## 2025-02-14 — Enforce strict bounds on wyoming network stream parsing
**Learning:** Wyoming network payload sizes and header lines could potentially be unlimited if not bounded, causing DoS attacks.
**Action:** Enforced max 64KB for header JSON size, 1MB max for payload / data length fields, and 2MB max for accumulated buffer sizes in `blitztext/wakeword.py` and `blitztext/wakeword_bench.py` before parsing occurs.
