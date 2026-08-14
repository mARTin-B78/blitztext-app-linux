## 2026-08-14 — [Wakeword Payload Bounds]
**Learning:** Wyoming network parser lacked bounds on incoming line lengths and parsed payload lengths.
**Action:** Enforced 64KB limits on socket streams in `wakeword.py` and `wakeword_bench.py` to mitigate DoS via memory exhaustion.
