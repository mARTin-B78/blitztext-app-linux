## 2024-05-18 — Unbounded network reads from Wyoming servers
 **Learning:** Wyoming servers push a payload_length followed by a payload block. `_drain_detections` and `_stream` previously did not enforce an upper limit on this payload, meaning an errant or malicious server could specify a payload of gigabytes, causing the app to read indefinitely or OOM.
 **Action:** We set a max threshold (10 MB limit) for `payload_length` parsed from a Wyoming server and raise a `ValueError` to break and recover when this limit is exceeded.
