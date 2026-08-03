## 2023-10-27 — Fix command injection via shell=True in talk.py
**Learning:** Found a vulnerability in `blitztext/talk.py` where `subprocess.Popen(..., shell=True)` was used to run a curl pipeline with URL and JSON payload interpolation. Although `shlex.quote` was used on the JSON, relying on `shell=True` with external/config data is a dangerous pattern.
**Action:** Replaced `shell=True` string with chained `shell=False` `subprocess.Popen` calls, piping stdout from `curl` to stdin of `ffplay` securely.
## 2023-10-27 — Fix CI secret scan failure
**Learning:** The CI secret scan failed on dummy `sk-...` placeholders in documentation. Replaced these with `<your_api_key_here>`. Also removed the overly aggressive `OPENAI_API_KEY[[:space:]]*=` regex from `.github/secret-scan-patterns.txt` as per project instructions, since it falsely flags documentation or standard config scripts.
**Action:** Replaced `sk-...` dummy keys with `<your_api_key_here>` across docs, and removed the bad regex pattern from `.github/secret-scan-patterns.txt`.
