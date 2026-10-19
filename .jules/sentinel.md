## 2026-10-19 — Bounded Wyoming network payload sizes
**Learning:** Wyoming protocol network streams read 'data_length' and 'payload_length' metadata from unverified network sources to allocate chunks and drain network sockets. An unauthenticated server returning excessively large numbers can cause unlimited memory allocation and loop processing blocks.
**Action:** Added explicit hard-limits to length properties on both properties in 'wakeword.py' loops and 'wakeword_bench.py'. The connection is dropped to prevent indefinite blocking.
