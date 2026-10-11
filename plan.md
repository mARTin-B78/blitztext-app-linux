1. **Explore the codebase and understand the vulnerability.**
   - Review `wakeword.py` and `wakeword_bench.py` where network payloads are read using `payload_length` and `data_length`.
   - Confirm that large values for these fields can cause memory exhaustion or endless reading (DoS).

2. **Add bounds to `payload_length` and `data_length`.**
   - In `wakeword.py`'s `WakewordListener._stream` (line 117) and `WakewordEngineStreamer._run` (line 283), add validation to ensure `data_length` and `payload_length` do not exceed a sensible limit (e.g., `1048576` bytes or 1MB).
   - If they exceed this limit, raise a `ValueError` to break the connection loop rather than quietly returning (which would block or hang).
   - Similarly, in `wakeword_bench.py`'s `_drain_detections`, ensure `payload_length` is bounded, raising a `ValueError` if it's too large.

3. **Add a regression test.**
   - Modify `tests/test_wakeword_bench.py` or create a new test file `tests/test_security_wakeword.py`.
   - Add a test that passes a JSON header with an artificially huge `payload_length` to `_drain_detections` and verifies that it raises `ValueError`.

4. **Verify the changes.**
   - Run the test suite using `pytest tests/test_wakeword_bench.py` and `pytest tests/test_security_wakeword.py`.
   - Run the pre-commit checks and linters using `ruff check blitztext tests`.

5. **Complete pre-commit steps to ensure proper testing, verification, review, and reflection are done.**

6. **Submit PR.**
   - Title: `🛡️ Sentinel: Bounds on wyoming network payloads`
   - Include What, Why, Risk, Verified, and Scope sections.
