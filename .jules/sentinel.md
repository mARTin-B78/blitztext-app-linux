## 2026-10-12 — [Sentinel Wakeword DoS]
 **Learning:** Unbounded read vulnerabilities in network parsing loops need explicit length checks to break the loop or raise exceptions.
 **Action:** Added ValueError exception on data_length and payload_length > 10MB in wakeword.py and wakeword_bench.py to prevent DoS.
