## 2024-10-11 — [Bounds on wyoming network payloads]
**Learning:** Parsing network lengths directly from JSON elements can cause Denial of Service loops if large lengths are provided maliciously and exceptions are not raised correctly.
**Action:** Bounded `data_length` and `payload_length` to 1MB when parsed. Raised `ValueError` if exceeded.
