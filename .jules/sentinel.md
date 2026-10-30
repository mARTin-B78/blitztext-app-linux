## 2024-10-31 — [Sentinel] Enforce payload_length bounds in Wyoming protocol
**Learning:** Network endpoints in `wakeword.py` and `wakeword_bench.py` accept unbounded `data_length` and `payload_length` values from the Wyoming protocol stream, which could lead to a Denial-of-Service condition (excessive memory allocation or an indefinitely blocking loop on `recv()`).
**Action:** Enforced an upper limit bounds check of `1048576` (1MB) on `data_length` and `payload_length` variables in `WakewordListener._stream`, `WakewordActionListener._stream`, and `_drain_detections`. Added a regression test (`test_sentinel_wakeword.py`) to verify the check triggers `ValueError`.
**Action:** Reverted extraneous modified files due to false positive key replacements and scrubbed out test artifacts.
