## 2026-09-29 — [talk: command injection via shell=True]
**Learning:** Found a command injection vulnerability where a configuration-derived URL was passed into `subprocess.Popen(cmd, shell=True)` for `curl | ffplay`.
**Action:** Replaced `shell=True` with chained `subprocess.Popen` executions passing argument lists directly. Added a focused security test.