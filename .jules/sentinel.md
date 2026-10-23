## 2026-10-23 — [Fix Wakeword Network Unbounded Read/DoS]
**Learning:** The Wyoming protocol network reader had unbounded limits for data_length and payload_length which could result in DoS/memory exhaustion if connected to an untrusted source.
**Action:** Enforced a 4MB limit on data_length and payload_length in WakewordListener, WakewordActionListener, and _drain_detections.
