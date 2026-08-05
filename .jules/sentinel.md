## 2025-02-05 — Network Stream Bounding
**Learning:** Socket network reading logic requires hard truncation on memory buffers and JSON-stated payload lengths to prevent remote DoS (e.g. allocating massive arrays for payloads that are never fully provided).
**Action:** Enforced strict 64KB bounds checks when parsing `payload_length`, `data_length`, and newline JSON headers in `wakeword.py` and `wakeword_bench.py`, raising an exception to sever the connection on malicious lengths instead of soft truncation that desyncs streams.
