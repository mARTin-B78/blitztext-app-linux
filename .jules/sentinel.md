## 2024-05-18 — Unbounded read in network loop
**Learning:** Missing bounds checks on network lengths can cause DoS or OOM.
**Action:** Added bounds checking for payload_length and data_length in wakeword.py and wakeword_bench.py to break unbounded read loop.
