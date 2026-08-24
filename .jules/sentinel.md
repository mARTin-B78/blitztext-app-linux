## 2026-07-07 — Shell Injection in Blitztalk

**Learning:** `talk.py` passes the TTS payload to a subprocess pipe using `shell=True`, which is susceptible to shell injection even if `shlex.quote` is used (since `extra_payload` can inject arbitrary content, and handling quoting properly for all scenarios is difficult). Additionally, `xdotool` type parameters have the same potential if not handled carefully, though in `paste.py` we use `shell=False`.
**Action:** Replaced `subprocess.Popen(..., shell=True)` pipeline with chained `subprocess.Popen(..., shell=False)` calls linking stdout to stdin. Removed the use of `shlex.quote()` as the `subprocess` API with lists handles arguments properly without extra quoting. Added a mock-based test `test_talk_security.py` to prevent regressions.
