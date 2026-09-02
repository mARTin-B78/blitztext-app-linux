## 2026-09-02 — Shell Injection in talk.py
**Learning:** `talk.py` uses `subprocess.Popen(..., shell=True)` with string formatting containing a `url` variable which could lead to command injection if the URL is malicious. Although `safe_payload` is quoted, `url` is not.
**Action:** Removed `shell=True` from `subprocess.Popen` in `talk.py` by converting the pipeline into two separate `subprocess.Popen` calls connected via `subprocess.PIPE`. Unused `shlex` module was also removed.
