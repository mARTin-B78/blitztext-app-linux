## 2026-10-15 — [Fix unbounded read vulnerability in wakeword stream parsing]
 **Learning:** Unbounded payload_length and data_length values in network parsing loops can lead to denial-of-service via resource exhaustion.
 **Action:** Added bounds checking to enforce a 1MB limit and raise ValueError when exceeded in wakeword.py and wakeword_bench.py.
