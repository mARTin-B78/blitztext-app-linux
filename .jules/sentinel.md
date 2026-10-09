## 2024-06-03 — Command injection in talk.py
**Learning:** The `talk.py` file used `subprocess.run` with `shell=True` to stream audio, making it vulnerable to command injection via the URL or extra payload fields.
**Action:** Replaced `shell=True` and the bash pipeline with `subprocess.Popen` and `subprocess.run` using explicit lists of arguments. Removed `shlex`. Added regression test `test_sentinel_talk.py`.
