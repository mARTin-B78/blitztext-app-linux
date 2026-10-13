
## 2024-10-24 — [Bound wakeword payload limits to prevent DoS]
**Learning:** The wakeword event parser trusted arbitrary payload_length and data_length values from the network, which could trigger unbounded reads resulting in resource exhaustion.
**Action:** Added a 10MB strict limit for data_length and payload_length values across WakewordListener, WakewordActionListener, and bench scripts, raising ValueError to safely abort the parse loop.
