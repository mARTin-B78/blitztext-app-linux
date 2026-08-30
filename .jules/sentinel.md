## 2026-08-30 — Fix shell injection in talk.py
 **Learning:** Using shell=True with string formatting can introduce injection vulnerabilities. Refactored into a list of arguments without shell=True.
 **Action:** Removed shell=True in talk.py.
