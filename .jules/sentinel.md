## 2026-11-07 — [Bound Wyoming payload lengths]
**Learning:** Unvalidated payload/data length values from the Wyoming protocol parsing could lead to indefinite blocking/DoS.
**Action:** Bounded data_length and payload_length values to be between 0 and 1MB and raise ValueError on failure to terminate connections early.
