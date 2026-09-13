## 2024-05-18 — [Sentinel Fix]
**Learning:** Found shell injection in `talk.py` TTS player. `subprocess.Popen(..., shell=True)` combined with shell pipelines (`|`) requires shell evaluation, exposing command injection vectors. `shlex.quote()` should not be used with `shell=False` as `Popen` handles escaping.
**Action:** Removed `shell=True` and separated the pipeline into two `subprocess.Popen` calls, piping stdout. Removed `shlex.quote()` on JSON payloads.
