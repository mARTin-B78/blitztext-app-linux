## 2024-05-30 — Unbounded payload and headers in Wyoming stream

**Learning:** When parsing untrusted socket streams like the Wyoming protocol, explicitly bound header lengths and payload loops to prevent DoS via unbounded memory allocation.
**Action:** Enforced 64KB limits on headers and 1MB bounds on data/payload lengths in `wakeword.py`, and capped the memory accumulation in `wakeword_bench.py` to 1.1MB.
