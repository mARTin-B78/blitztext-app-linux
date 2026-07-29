## 2026-07-29 — Fix command injection in TTS playback
**Learning:** Found `subprocess.Popen(..., shell=True)` in `talk.py` where `url` from config was unsafely interpolated into a shell pipeline. Replaced with chained `subprocess.Popen(..., shell=False)` to securely handle piped commands without shell evaluation.
**Action:** Removed `shell=True`, removed `shlex` quoting for json, and chained the `curl` and `ffplay` processes using stdout to stdin pipes with parent process fd closure.
