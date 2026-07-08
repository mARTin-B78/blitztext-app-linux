## 2023-10-27 — [Wyoming DoS Fix]
**Learning:** Network streams in Python sockets parsing Wyoming headers can lead to unconstrained unbounded reads, causing Denial of Service via memory exhaustion if an attacker omits newlines or sends huge `payload_length` values. When breaking out of oversized headers, we must `return` immediately so the truncated string doesn't get passed to `json.loads` and crash the thread.
**Action:** Enforced 64KB line bounds and 1MB buffer/payload lengths in `wakeword.py` and `wakeword_bench.py` and exited gracefully.
