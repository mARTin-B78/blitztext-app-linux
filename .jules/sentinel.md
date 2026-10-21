## 2024-05-24 — Unbounded Resource Read in Wyoming Sockets
**Learning:** Out-of-bounds `data_length` and `payload_length` properties in Wyoming JSON payloads allow DoS through huge memory allocations or socket blocking.
**Action:** Bounded data_length and payload_length sizes in `wakeword.py` stream methods and `wakeword_bench.py` parsing loops.
