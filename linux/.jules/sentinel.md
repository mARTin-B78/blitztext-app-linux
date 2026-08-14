## 2026-08-14 — [Wakeword Payload Bounds]
**Learning:** Wyoming network parser lacked bounds on incoming line lengths and parsed payload lengths.
**Action:** Enforced 64KB limits on socket streams in `wakeword.py` and `wakeword_bench.py` to mitigate DoS via memory exhaustion.
## 2026-08-14 — [Secret Scanner False Positives]
**Learning:** The GitHub Actions CI secret scanner was tripping on harmless `<your-api-key>` style documentation placeholders, breaking builds that contained instructions like `export OPENAI_API_KEY=sk-...`.
**Action:** Updated `.github/secret-scan-patterns.txt` to ignore the `<your-api-key>` placeholder while still matching real keys. Replaced all dummy `sk-...` placeholders across documentation (`README.md`, `docs/setup.md`, `install-linux.sh`, etc.) with safe placeholders to resolve the CI failure.
