## 2026-11-10 — [Fix Unbounded Read DoS in Wyoming Protocol]
 **Learning:** Wyoming protocol network payloads were parsed without checking lengths, which can cause an unbounded read DoS attack.
 **Action:** Added a 1MB bound to payload/data length fields in `wakeword.py`, `wakeword_bench.py`, and `gtksettings.py` to mitigate unbounded reads.
