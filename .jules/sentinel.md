## 2024-05-16 — Unbounded JSON parsing and buffer growth
 **Learning:** In `wakeword.py` and `wakeword_bench.py`, Wyoming protocol payloads are read off the wire without boundary limits. An oversized JSON payload or declared binary payload could cause an unbounded read resulting in a DoS via memory exhaustion.
 **Action:** Bounded line accumulators to 64KB and explicitly checked `payload_length` values to be non-negative and capped at 1MB to prevent infinite/exhausting reads.
