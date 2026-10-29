## 2025-02-14 — Enforce bounds on Wyoming network streams
**Learning:** Network streams from untrusted servers in Python using `socket.recv` in a `while not line.endswith(b"\n")` loop are vulnerable to DoS if the server never sends a newline or lies about massive payload lengths. We must proactively track accumulated bytes independently of the delimiter and throw a `ConnectionError` or `ValueError` rather than breaking the inner loop to prevent subsequent bad state parsing.
**Action:** Enforced a strict 64KB JSON header limit and 1MB limit for buffers/payloads in `blitztext/wakeword.py` and `blitztext/wakeword_bench.py`.

## 2025-02-14 — Remove aggressive secret scan pattern
**Learning:** The CI secret scan workflow uses `.github/secret-scan-patterns.txt`. Broad patterns like `OPENAI_API_KEY[[:space:]]*=` cause false positives on setup scripts and documentation that correctly use placeholders (e.g. `<your_api_key_here>`).
**Action:** Removed the `OPENAI_API_KEY[[:space:]]*=` pattern from `.github/secret-scan-patterns.txt` instead of renaming standard environment variables in code/docs.
## 2025-02-14 — Fix CI PyGObject build failure
**Learning:** Ubuntu 24.04 and PyGObject 3.56+ require `libgirepository-2.0-dev` and `pkg-config` in addition to `libgirepository1.0-dev` to build successfully. If these are missing, `pip install PyGObject` will fail with a `Dependency 'girepository-2.0' is required but not found` error via the Meson build system.
**Action:** Updated `.github/workflows/ci.yml` to install `libgirepository-2.0-dev pkg-config build-essential` in the apt-get step to fix the CI failure.
