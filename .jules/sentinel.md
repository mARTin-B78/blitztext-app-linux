## 2025-02-28 — Unbounded read DoS risk fixed in Wyoming protocol
**Learning:** Found an unbounded read DoS risk in the json-lines processing of the Wyoming wakeword protocol within `blitztext/wakeword.py` and `blitztext/wakeword_bench.py`, where `data_length`, `payload_length`, and newline reading were blindly trusted, potentially allowing remote server responses to exhaust memory.
**Action:** Enforced strict 64KB limits on lengths during protocol parsing in the listeners and benchmark drain loops to abort the connection on malicious sizes.
