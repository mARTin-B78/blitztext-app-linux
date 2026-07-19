## 2024-07-19 — Added bounds check for payload lengths in wakeword network parser
**Learning:** Wyoming protocol network sockets reading loops need bounds limits on header and payload structures. They use unbounded `while` loops that can exhaust memory.
**Action:** Implemented 64KB hard limits on header lengths and 1MB on payloads in `wakeword.py` and `wakeword_bench.py` when decoding JSON.
