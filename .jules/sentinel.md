## 2025-02-23 — [Fix Unbounded Read DoS in Wakeword]
**Learning:** Unbounded sizes parsed from network protocols like Wyoming can lead to denial-of-service.
**Action:** Bounded data and payload lengths to 10MB in `wakeword.py` and `wakeword_bench.py` and raised exceptions.
