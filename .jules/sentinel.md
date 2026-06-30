## 2024-06-30 — Bounding Wyoming Protocol Buffer Reads
**Learning:** Network streams using the Wyoming protocol in `wakeword.py` and `wakeword_bench.py` did not inherently limit the sizes of lines, headers, or payloads, meaning a rogue server could return endlessly and exhaust memory in DoS attacks.
**Action:** Capped JSON parsing arrays / `payload_length` loop allocations to 64KB and 1MB thresholds. Verified functionality using the established test suite ensuring no functional regressions while strictly restricting DoS limits.
