## 2024-05-24 — [Predictable temp paths for MUTE_FILE]
 **Learning:** The MUTE_FILE flag path was hardcoded to `/tmp/wake_muted`. In a shared multi-user environment, predictable file paths in world-writable directories like `/tmp` can lead to symlink race vulnerabilities.
 **Action:** Changed `MUTE_FILE` in `linux/blitztext/wakeword.py` to use a safe, user-owned directory (`XDG_RUNTIME_DIR` or `~/.cache`), preventing unauthorized manipulation or symlink attacks.
