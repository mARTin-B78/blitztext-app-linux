## 2024-10-11 — [Bounds on wyoming network payloads]
**Learning:** Parsing network lengths directly from JSON elements can cause Denial of Service loops if large lengths are provided maliciously and exceptions are not raised correctly.
**Action:** Bounded `data_length` and `payload_length` to 1MB when parsed. Raised `ValueError` if exceeded.

## 2024-10-11 — [Ignore dummy OPENAI_API_KEY in secret scanner]
**Learning:** CI secret scanners may fail on dummy keys in documentation. Renaming variables breaks setup instructions, but updating the scanner's regex pattern using a negative lookahead provides a clean workaround.
**Action:** Updated `.github/secret-scan-patterns.txt` to use `(?!sk-\.\.\.)` negative lookahead and changed the CI scan to use `grep -P`.
