## 2026-09-07 — shell=True injection vector
 **Learning:** Using shell=True with subprocess.Popen creates a command injection vector, particularly when handling network payloads.
 **Action:** Refactored shell pipeline to explicitly chain multiple subprocess.Popen calls with PIPE without using shell=True or shlex.
