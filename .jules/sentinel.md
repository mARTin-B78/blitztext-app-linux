## 2026-10-07 — Fix DoS from unbounded network lengths in Wyoming protocol
 **Learning:** Unbounded read lengths can cause DoS.
 **Action:** Added bounds checking for data_length and payload_length in Wyoming protocol listeners.
