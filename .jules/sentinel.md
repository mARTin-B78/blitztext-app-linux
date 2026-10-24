## 2026-10-18 — [Fix Command Injection in TTS Playback]
 **Learning:** Identified a command injection vulnerability where `subprocess.run(cmd, shell=True)` was used to pass TTS request values, making it vulnerable to URL injections.
 **Action:** Replaced `subprocess.run(cmd, shell=True)` with a chained `subprocess.Popen` implementation using proper argument lists.
