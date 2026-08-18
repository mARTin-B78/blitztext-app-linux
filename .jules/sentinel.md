
## 2024-05-20 — Refactored `shell=True` execution in audio playback
**Learning:** Configurable or user-provided values (like the text payload) passed into a subprocess using `shell=True` present a severe risk of command injection. Using `shlex.quote` is an incomplete mitigation compared to avoiding the shell entirely.
**Action:** Removed `shell=True` in `linux/blitztext/talk.py` by converting the command string into an argument list and manually connecting the stdout of `curl` to the stdin of `ffplay` using `subprocess.PIPE`.
