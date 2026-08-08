## 2024-05-24 — [Initial Setup]
**Learning:** Initial journal creation.
**Action:** None.
## 2024-05-24 — [Enforce Hard Limits on Untrusted Socket Streams]
**Learning:** Unbounded reads without delimiter checks or max-payload bounds can allow a malicious or misconfigured server to exhaust client memory and DoS the application.
**Action:** Added 64KB hard limits to socket reads in `wakeword.py` and `wakeword_bench.py` when parsing untrusted JSON streams from the wake-word server.
