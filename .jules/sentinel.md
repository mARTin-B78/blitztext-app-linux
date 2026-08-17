## 2026-08-17 — [Fix command injection in text-to-speech engine]
 **Learning:** Refactored `subprocess.Popen(cmd, shell=True)` in `blitztext/talk.py` to use `shell=False` by piping `curl` to `ffplay` using Python's subprocess pipeline directly, eliminating a command injection vulnerability.
 **Action:** Removed `shell=True` and `shlex.quote`, replaced it with piped subprocess commands.
