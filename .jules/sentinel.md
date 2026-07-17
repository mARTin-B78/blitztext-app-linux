## 2026-07-07 — Bounded network reads for Wyoming protocol
 **Learning:** The custom wyoming-openwakeword integration in `wakeword.py` and `wakeword_bench.py` had unbounded loops for stream parsing, posing a potential DoS risk from malformed packets lacking newline delimiters.
 **Action:** Enforced max byte limits on json headers (64KB) and payload structures (1MB) to safely drop malicious/corrupted network traffic gracefully via `ConnectionError` and `ValueError`. Fixed socket read logic to raise standard exceptions on early EOF instead of hanging or spinning.
