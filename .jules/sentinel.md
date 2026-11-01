## 2026-11-01 — [Fix RCE in talk.py TTS engine url handling]
**Learning:** Shell=True combined with dynamically provided or configured string content is a high risk vulnerability. In this case, `url` was not sanitized before formatting in a subprocess shell string.
**Action:** Replaced `subprocess.run(shell=True)` pipeline with `subprocess.Popen` direct calls to `curl` and `ffplay` passing arguments as a list. Wrote a regression test testing for `shell=False` execution logic.
