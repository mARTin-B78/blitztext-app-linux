## 2026-09-10 — [Remove shell injection vector in talk.py]
**Learning:** `talk.py` passes dynamically built, unvalidated configuration strings into a `subprocess.Popen` call using `shell=True`, introducing an arbitrary shell execution vulnerability when chained with potentially user-controlled configuration values.
**Action:** Removed `shell=True` and `shlex.quote` in `talk.py` in favor of argument lists and chained `subprocess.Popen` calls using `subprocess.PIPE`.
