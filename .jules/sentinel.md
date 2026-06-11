
## 2024-05-27 — Bounding untrusted network payload reads
**Learning:** Wyoming protocol network payloads are parsed manually using length headers. If these headers are unbounded, reading the network stream can cause a DoS (e.g. by hanging the worker or exhausting memory).
**Action:** Bounded the `payload_length` parsed from Wyoming JSON detection messages to a max of 10MB in `wakeword.py` and `wakeword_bench.py` before iterating network reads.
