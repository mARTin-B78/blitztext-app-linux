## 2024-05-15 — Wyoming Protocol Denial of Service
**Learning:** Wyoming protocol handlers blindly trusted `payload_length` and `data_length`, allowing unbound memory reads and DoS.
**Action:** Added explicit limits (10MB for payload, 1MB for data) raising ValueError for malicious values.
