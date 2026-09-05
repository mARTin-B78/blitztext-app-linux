## 2024-07-25 — Untrusted Network Parsing Bounds
**Learning:** The Wyoming protocol implementation in `wakeword.py` and `wakeword_bench.py` parses network streams (JSON headers + binary payloads). An unbounded stream missing newlines, or claiming massive `payload_length` or `data_length`, could lead to DoS via memory exhaustion.
**Action:** Enforced 64KB max bounds on header/data lengths and a 1MB bound on `payload_length`. Bounded `len(line)` while byte-reading and `len(buf)` before `split(b"\\n")`.
