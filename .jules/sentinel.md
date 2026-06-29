
## 2024-05-18 — Buffer Unbounded Reads in Wyoming Streams
**Learning:** Wyoming network streams parse headers via finding newlines (`\n`) and reading binary `data_length`/`payload_length` chunks. Without bounds, a stream lacking a delimiter or claiming huge payload dimensions causes unbounded `recv()` calls or infinite memory buffering, leading to DoS.
**Action:** Enforced strict length limits on line parsing (64KB), JSON payload buffers (1MB), and binary audio chunk payloads (1MB) in `wakeword.py` (application) and `wakeword_bench.py` (testing utility) to reject over-sized bounds safely.
