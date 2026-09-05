## 2024-10-24 — [Bound Wyoming payload length]
 **Learning:** Wyoming server responses include a `payload_length` parameter that dictates how many subsequent bytes to read from the network. Without bounds checking, this creates a Denial of Service (DoS) vulnerability (unbounded reads/allocations) via malicious network payloads.
 **Action:** Added type checking and an upper bound limit of 10MB to `payload_length` parsing in `wakeword.py` and `wakeword_bench.py`.
