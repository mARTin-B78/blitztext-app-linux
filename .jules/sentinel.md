## 2024-05-18 — [Wyoming Protocol parser unbounded read DoS]
**Learning:** Found that the Wyoming protocol parser trusts payload_length and data_length from remote endpoints without bounds checking, which allows an attacker to tie up main loop threads and consume connection slots.
**Action:** Capped payload_length and data_length at 10MB, raising a ValueError on violation.
