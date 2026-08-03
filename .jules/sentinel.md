## 2023-10-27 — Fix command injection via shell=True in talk.py
**Learning:** Found a vulnerability in `blitztext/talk.py` where `subprocess.Popen(..., shell=True)` was used to run a curl pipeline with URL and JSON payload interpolation. Although `shlex.quote` was used on the JSON, relying on `shell=True` with external/config data is a dangerous pattern.
**Action:** Replaced `shell=True` string with chained `shell=False` `subprocess.Popen` calls, piping stdout from `curl` to stdin of `ffplay` securely.
