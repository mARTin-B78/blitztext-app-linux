## 2026-09-18 — [Command Injection in TTS playback]
**Learning:** Using `shell=True` with string formatting for `subprocess.Popen` allows command injection if input parameters like URL are unquoted and controlled by configuration.
**Action:** Replaced `shell=True` pipeline with safely chained `subprocess.Popen` calls using `subprocess.PIPE` without a shell.
