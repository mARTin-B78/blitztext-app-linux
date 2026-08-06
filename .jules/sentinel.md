## 2026-08-06 — Command injection in talk.py
 **Learning:** `subprocess.Popen(cmd, shell=True)` with user/config-derived `cmd` in `talk.py` is a command injection vector.
 **Action:** Refactored `talk.py` to use `subprocess.Popen` with `shell=False` or `subprocess.run`, securely piping output where needed.
