# Sentinel Journal
## 2026-07-27 — [Enforce bounds on Wyoming network streams]
**Learning:** The Wyoming protocol implementation dynamically parsed newline-framed JSON and binary payloads from untrusted network socket streams without enforcing upper bounds on the buffer lengths. This could allow a malicious server to cause Denial of Service (DoS) via unbounded memory allocation on deliberately malformed network streams (e.g., streaming indefinitely without sending a newline).
**Action:** Implemented bounds in `wakeword.py` and `wakeword_bench.py` that drop the stream (`ConnectionError`) if the header line length exceeds 64KB or if the buffer/payload lengths exceed 1MB.
