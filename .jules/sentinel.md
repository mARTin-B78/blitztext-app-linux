## 2024-06-11 — Fix shell=True injection risk in TTS audio streaming
**Learning:** Replaced `shell=True` involving `curl` and `ffplay` with a secure chained `subprocess.Popen` pipeline in `talk.py`. When chaining `subprocess.Popen`, it is crucial to close the `stdout` of the first process (e.g., `curl_proc.stdout.close()`) in the parent process to allow standard SIGPIPE delivery if the second process (`ffplay`) terminates early.
**Action:** Removed command injection vulnerability in `talk.py` by converting to a list-based `subprocess` invocation without `shell=True`.
