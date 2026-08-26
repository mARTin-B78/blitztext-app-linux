## 2026-06-07 — Command Injection in `blitztext/talk.py`
**Learning:** `blitztext/talk.py` passes `safe_payload` inside `subprocess.Popen(cmd, shell=True)` for `curl | ffplay`. Although the payload is passed through `shlex.quote`, using `shell=True` is generally insecure and violates the rule "any `subprocess` with `shell=True`" from the checklist.
**Action:** Refactored `talk.py` to use `shell=False` and separate `subprocess.Popen` calls connected via `subprocess.PIPE`.
