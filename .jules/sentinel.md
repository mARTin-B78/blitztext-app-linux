## $(date +%Y-%m-%d) — Enforce bounds on untrusted network stream reads
**Learning:** Parsing untrusted network streams requires validating buffer sizes before locating delimiters to prevent Denial of Service via unbounded memory allocation.
**Action:** Enforced 64KB header bounds, 1MB data/payload bounds, and ensured correct exception handling on truncated reads in `wakeword.py` and `wakeword_bench.py`.
