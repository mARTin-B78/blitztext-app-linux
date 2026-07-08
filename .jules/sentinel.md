## 2024-05-18 — [Wyoming Protocol Parsing]
**Learning:** Wyoming protocol network parsing loops (`wakeword.py` and `wakeword_bench.py`) are susceptible to resource exhaustion (DoS) via unbounded header line reads, huge `data_length` arrays, or infinite binary block draining based on manipulated `payload_length` values. Memory bounds checks must be strictly applied before `sock.recv` calls.
**Action:** Enforced 65KB limits on JSON metadata headers and 1MB bounds on binary chunk payloads and buffer aggregators in all listeners to gracefully drop excessively large messages.
