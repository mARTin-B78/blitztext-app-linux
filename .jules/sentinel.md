## 2024-05-18 — [Mitigating command injection via Popen shell]
**Learning:** Avoid `subprocess.Popen(..., shell=True)` with dynamically constructed strings. Using chained `subprocess.Popen` calls correctly protects against shell command injection when untrusted arguments (e.g. from configurations) are passed to system commands like curl.
**Action:** Replaced `subprocess.Popen` with `shell=True` and f-strings inside `blitztext/talk.py` with chained `subprocess.Popen` processes avoiding shell injection, safely passing url and payloads as list elements.
