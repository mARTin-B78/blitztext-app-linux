## 2024-05-18 — Refactored bash pipeline to avoid shell injection
**Learning:** Found `subprocess.Popen` in `blitztext/talk.py` running `curl ... | ffplay ...` with `shell=True` and a string-interpolated URL. While the payload was safely quoted with `shlex.quote()`, the URL itself was vulnerable to shell injection if constructed maliciously.
**Action:** Refactored the command to use a list of arguments and `shell=False` to securely launch `curl`, and pipelined it to a second `subprocess.Popen` executing `ffplay`, allowing `curl` to receive a `SIGPIPE` upon early exit via `p1.stdout.close()`.
