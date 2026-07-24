
## $(date +%Y-%m-%d) — Unbounded parsing in Wyoming protocol client
**Learning:** Found an unbounded memory allocation DoS vulnerability when parsing untrusted streaming network responses from Wyoming endpoints (`wakeword.py`, `wakeword_bench.py`). The byte-reading loops checking for `\n` would grow infinitely if `\n` was omitted by an attacker. Additionally, Wyoming's payload lengths were fully trusted, which could result in a massive one-time read request if spoofed.
**Action:** Enforced max byte sizes (64KB for JSON header, 1MB for data payload) across socket parsing and byte splits, dropping malformed payloads with a `ValueError`. Changed EOF inner-loop behavior from `break` to `return` to properly skip broken JSON loading.
