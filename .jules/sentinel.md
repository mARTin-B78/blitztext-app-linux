## 2024-05-18 — [Wakeword Payload Lengths]
**Learning:** Wyoming network endpoints parsing framing protocols must bound header lengths to 64KB and payload lengths to 1MB to avoid DoS memory spikes.
**Action:** Added explicit limits in parsing logic for wakeword.py and wakeword_bench.py.
## 2024-05-18 — [Secret Pattern Avoidance]
**Learning:** CI secret scanner complains on any exact string OPENAI_API_KEY=, even in docs. We should not have touched docs.
**Action:** Reverting accidental doc changes.
