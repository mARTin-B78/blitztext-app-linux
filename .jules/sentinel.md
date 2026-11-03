## 2026-11-02 — [Sentinel] Wakeword Unbounded Read
**Learning:** Wyoming protocol network payloads specified by `payload_length` or `data_length` need upper bounds. Without bounds, a malicious/compromised server can send massive lengths, causing denial of service through unbounded blocking reads and memory exhaustion.
**Action:** Added 1MB bounds checking for both `data_length` and `payload_length` in `wakeword.py` and `wakeword_bench.py`, raising a `ValueError` if exceeded. Added security regression tests to `test_wakeword_stream.py` and `test_wakeword_bench.py`.
