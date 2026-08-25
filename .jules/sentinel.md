## 2026-08-25 — [Sentinel Fix]
 **Learning:** When refactoring a shell pipeline to avoid shell=True, you must explicitly close the first process's stdout in the parent process (e.g., p1.stdout.close()) after passing it to the second process's stdin to prevent deadlocks.
 **Action:** Removed shell=True from talk.py TTS pipeline.
