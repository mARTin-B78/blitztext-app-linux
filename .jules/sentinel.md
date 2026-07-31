## 2024-07-31 — [Security] Fix untrusted network streams parsing lengths

**Learning:** Unbounded read loops over socket streams can cause Denial of Service (DoS) attacks from malformed protocol messages (like oversized headers or arbitrary binary payloads) if a maximum length limit is not strictly enforced. In Python `subprocess` chains, `shell=True` exposes the command to arbitrary injection if network-derived config (e.g. from TTSEngine payload dicts) gets interpolated into the shell command string without stringent validation. Also, `subprocess.Popen` in chained sub-processes needs correct stdout closing for the upstream command so it receives SIGPIPE when downstream ends.

**Action:**
- Replaced `shell=True` with array-based command structures in `talk.py` via chaining processes (for `curl` piped to `ffplay`), closing `p1.stdout` in the parent process.
- Implemented maximum string bounds in Wyoming socket reader logic in `wakeword.py` (preventing DoS from 10GB payloads causing memory allocation issues on client).
- Implemented buffer size checks within `wakeword_bench.py` when decoding server feedback on benchmarks.
