## 2024-05-18 — Unbounded network reads in wakeword listeners
 **Learning:** Unbounded payload_length values from untracked servers can lead to arbitrary memory allocation and DoS.
 **Action:** Added a 1MB bound to data_length and payload_length parsed from wakeword servers.
