
## 2026-06-16 — [Fix DoS vector in wakeword networking]
 **Learning:** Untrusted data parsing from network sockets lacking length bounds exposes the client to memory exhaustion and DoS attacks. The `wakeword.py` networking logic and `wakeword_bench.py` parsed JSON payload metadata without validating limits.
 **Action:** Enforced strict bounds on incoming data sizes: maximum line read length set to 64KB and payload chunk lengths capped to 10MB to prevent resource starvation.
