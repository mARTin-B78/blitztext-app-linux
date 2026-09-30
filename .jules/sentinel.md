## 2026-09-30 — [talk.py URL Command Injection]
 **Learning:** Using `shell=True` with string formatting for URLs exposes a command injection vulnerability when reading configuration values that aren't sanitized.
 **Action:** Replaced the `curl ... | ffplay` pipeline string passed to `shell=True` with chained `subprocess.Popen` calls using `subprocess.PIPE`, avoiding a shell entirely.
