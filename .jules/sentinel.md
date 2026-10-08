## 2026-10-18 — [Payload Bounds Validation]
 **Learning:** Untrusted length attributes from remote connections can cause DoS unbounded loops.
 **Action:** Added limit checks of 1MB on data_length and payload_length values during network reads.
