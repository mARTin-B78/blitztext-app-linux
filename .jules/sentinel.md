## 2026-06-27 — Prevent Untrusted Parsing DoS in wakeword modules
**Learning:** Network streams using the Wyoming protocol parse newline-terminated headers and byte payloads. If an endpoint deliberately omits a newline or sends massive lengths, it could trigger unbounded reads, causing a Denial of Service.
**Action:** Enforced max bounds: 64KB for line header parsing, and 1MB for `data_length` and `payload_length` allocations, preventing silent memory exhaustion during untrusted network interactions.
