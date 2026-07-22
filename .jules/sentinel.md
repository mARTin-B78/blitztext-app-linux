
## 2024-05-24 — [Enforce bounds on Wyoming network streams]
**Learning:** Parsing JSON headers or consuming raw binary payloads from Wyoming streams without asserting an explicit maximum buffer allocation length allows unauthenticated clients to trigger a memory-based Denial of Service (DoS).
**Action:** Enforced static size limits on incoming chunks: lines capped at 64KB, payloads capped at 1MB in both the standard implementation `wakeword.py` and the benchmark suite `wakeword_bench.py` before stream appending/consumption.

## 2024-05-24 — [Add libgirepository-2.0-dev to fix PyGObject build on CI]
**Learning:** PyGObject 3.56+ explicitly requires the `girepository-2.0` native system dependency to compile via meson, and omitting it causes metadata-generation failures in CI environments like GitHub Actions running Ubuntu 24.04.
**Action:** Added `libgirepository-2.0-dev` to the `.github/workflows/ci.yml` APT dependencies.
