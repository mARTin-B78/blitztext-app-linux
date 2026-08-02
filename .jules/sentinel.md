## 2025-02-14 — Enforce payload size limits to prevent DoS via unbounded reads
**Learning:** The Wyoming protocol implementation in `wakeword.py` and `wakeword_bench.py` lacked bounds on JSON header lengths and binary payload lengths, which could lead to Denial of Service (DoS) via unbounded reads if an attacker sent a large payload or deliberately omitted newlines.
**Action:** Enforced a maximum bound of 64KB for JSON headers and 1MB for data/payload blocks in `WakewordListener`, `WakewordActionListener`, and `_drain_detections`. When limits are exceeded, a `ValueError` is cleanly raised to prevent memory exhaustion.
## 2025-02-14 — Fix CI build for PyGObject
**Learning:** The Ubuntu 24.04 GitHub Actions runner lacked `libgirepository-2.0-dev`, `pkg-config`, and `build-essential` when installing PyGObject 3.56+ from source, leading to a build failure.
**Action:** Updated `.github/workflows/ci.yml` to include the required dependencies.
