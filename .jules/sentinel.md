## 2026-09-03 — Fix command injection in text-to-speech
 **Learning:** Avoid using shell=True in subprocess.Popen, especially when handling untrusted inputs like text-to-speech payloads. Use separate subprocess.Popen calls connected via subprocess.PIPE instead.
 **Action:** Refactored curl | ffplay pipeline in talk.py to use safe subprocess.Popen calls.
