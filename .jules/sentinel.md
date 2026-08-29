## 2026-08-29 — Fix Command Injection in TTS Request
 **Learning:** Avoid using shell=True with user-provided config like URLs; use list-based Popen calls and manually pipe stdout to stdin for complex pipelines.
 **Action:** Refactored curl | ffplay command in talk.py to use chained Popen calls without shell=True.
