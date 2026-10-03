## 2026-10-03 — [Denial of Service via Unbounded Payload Read]
 **Learning:** Unbounded payload_length values from the network can cause DoS or memory exhaustion.
 **Action:** Added bounds checking for data_length and payload_length in wakeword.py and wakeword_bench.py network parsing loops.
