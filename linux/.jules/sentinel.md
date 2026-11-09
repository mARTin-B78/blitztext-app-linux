
## 2026-11-09 — [Enforce bounds on Wyoming payload lengths]
**Learning:** Wyoming protocol network parsers in `wakeword.py` and `wakeword_bench.py` were blindly trusting `data_length` and `payload_length` fields from unauthenticated local socket connections, which could lead to unbounded reads or DoS via memory exhaustion.
**Action:** Enforced a 10MB bounds limit on all dynamically parsed `payload_length` and `data_length` attributes in `_read_event_body` and `_drain_detections`.
