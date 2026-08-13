## 2023-10-24 — Fix untrusted payload lengths
**Learning:** Wyoming network protocol parsing is vulnerable to denial of service if unverified sizes are blindly allocated (e.g. `data_length` and `payload_length` fields in streaming JSONs). Both client components and diagnostic tools using this protocol need explicit input bounds limits.
**Action:** Enforced maximum limits (64KB max) on dynamic allocation sizes when reading wake-word detection payloads and their internal blocks to ensure out of memory or socket hangs do not occur on malicious/corrupt frames.
