## 2024-10-27 — Fix Command Injection in TTS Pipeline
 **Learning:** Using `subprocess.Popen` with `shell=True` alongside user-controlled or configured data, even with `shlex.quote`, poses a command injection risk. Shell pipelines should be refactored into explicitly connected `subprocess.Popen` objects passing `stdout=subprocess.PIPE`.
 **Action:** Refactored `blitztext/talk.py` to eliminate `shell=True` and explicitly chain `curl` and `ffplay` processes using a pipe.
