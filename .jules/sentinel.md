
## 2026-07-10 — Bound length of streams in network requests
 **Learning:** Bounding the line and chunk length to prevent denial of service vulnerability.
 **Action:** Added limit checks of payload_length and data_length for network socket streams to prevent DoS via unbounded memory allocation on streams deliberately lacking delimiters.
