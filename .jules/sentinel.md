## 2026-09-22 — Bound network read lengths
**Learning:** Untrusted network servers could specify huge data_length or payload_length values, causing indefinite reading and DoS.
**Action:** Bounded data_length and payload_length values, and raised ValueError when exceeded to immediately break out of the parsing loops.
