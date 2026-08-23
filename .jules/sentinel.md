
## $(date -u +%Y-%m-%d) — Refactor talk.py to remove shell injection vulnerability
 **Learning:** When eliminating `shell=True` in a `subprocess.Popen` call that uses a shell pipeline (`|`), refactor it into separate `subprocess.Popen` calls by passing the first process's `stdout=subprocess.PIPE` directly to the second process's `stdin`. Also ensure that `shlex.quote()` is removed from previously quoted arguments like JSON payloads, since `Popen` argument lists handle quoting automatically and keeping `shlex.quote()` will break the payload.
 **Action:** Removed `shell=True` and `shlex.quote()` in `linux/blitztext/talk.py` when executing `curl | ffplay`, breaking it into two separate `Popen` instances.
