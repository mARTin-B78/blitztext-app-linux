
## 2026-09-16 — Bound wakeword network lengths
**Learning:** Network payloads in wakeword processing were missing length bounds, risking memory exhaustion/DoS.
**Action:** Added 1MB limit on data_length and payload_length in wakeword.py and wakeword_bench.py.
