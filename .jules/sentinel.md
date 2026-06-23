## 2024-06-23 — Wyoming protocol bounds
**Learning:** Wyoming protocol network parsers in `wakeword.py` and `wakeword_bench.py` lacked explicit length bounds when reading `msg["data_length"]` and `msg["payload_length"]`. They also lacked max-length bounds on the header line and buffer accumulations, which could lead to DoS by unbounded memory allocation or blocking reads.
**Action:** Enforced a 64KB max on header strings, a 1MB limit on `data_length` and `payload_length`, and a 1MB max accumulation limit on the receive buffer in `wakeword_bench.py`.
