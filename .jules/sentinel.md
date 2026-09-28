## 2026-09-28 — [Fix wyoming unbounded read DoS]
**Learning:** wyoming-openwakeword network protocol framing (payload_length / data_length) could be spoofed with negative or gigantic sizes, leading to DoS.
**Action:** Validated payload and data lengths against upper (1MB) and lower bounds with type checks before socket reads across wakeword.py, wakeword_bench.py, and gtksettings.py.
