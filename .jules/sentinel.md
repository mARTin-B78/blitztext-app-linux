
## 2024-05-24 — [Enforce bounds on Wyoming network streams]
**Learning:** Parsing JSON headers or consuming raw binary payloads from Wyoming streams without asserting an explicit maximum buffer allocation length allows unauthenticated clients to trigger a memory-based Denial of Service (DoS).
**Action:** Enforced static size limits on incoming chunks: lines capped at 64KB, payloads capped at 1MB in both the standard implementation `wakeword.py` and the benchmark suite `wakeword_bench.py` before stream appending/consumption.
