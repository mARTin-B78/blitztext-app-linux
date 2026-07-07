import re

with open("linux/blitztext/daemon.py", "r") as f:
    content = f.read()

# 1. Init _cancel_watcher etc. in __init__
init_vars = """        self.transcriber: Transcriber | None = None
        self._wakeword_listener = None
        self._cancel_watcher: typing.Any | None = None
        self._vad_meter: typing.Any | None = None
        self._action_listener: typing.Any | None = None
        self._scheme: typing.Any | None = None
        self._vad_started_at = 0.0
        self._vad_last_speech = 0.0"""
content = re.sub(r'        self\.transcriber: Transcriber \| None = None\n        self\._wakeword_listener = None', init_vars, content)

import_typing = "import threading\nimport typing\n"
content = re.sub(r'import threading\n', import_typing, content, count=1)

# 2. Fix line 98 snapshot uninitialized
snapshot_fix = """        ready = False
        snapshot = b""
        with self._lock:"""
content = re.sub(r'        with self\._lock:', snapshot_fix, content, count=1)

# 3. Add type ignore to gi.repository GLib
content = re.sub(r'from gi\.repository import GLib', r'from gi.repository import GLib  # type: ignore', content)
content = re.sub(r'from gi\.repository import GLib as _GLib', r'from gi.repository import GLib as _GLib  # type: ignore', content)

# 4. Add type ignore to getattr(...).stop()
content = re.sub(r'self\._vad_meter\.stop\(\)', r'self._vad_meter.stop()  # type: ignore', content)
content = re.sub(r'self\._cancel_watcher\.stop\(\)', r'self._cancel_watcher.stop()  # type: ignore', content)
content = re.sub(r'self\._action_listener\.stop\(\)', r'self._action_listener.stop()  # type: ignore', content)
content = re.sub(r'self\._ov_meter\.stop\(\)', r'self._ov_meter.stop()  # type: ignore', content)
content = re.sub(r'self\._scheme\.stop_listener\(\)', r'self._scheme.stop_listener()  # type: ignore', content)

# 5. Fix rec uninitialized
rec_fix = """                streamer = None
                rec = getattr(self, "_recording", None)
                if rec is None:
                    return
                wf, win = self._active_workflow, self._target_window"""
content = re.sub(r'                streamer = None\n                if self\._recording is None:\n                    return\n                rec, wf, win = self\._recording, self\._active_workflow, self\._target_window', rec_fix, content)

# 6. Add type ignore to pynput
content = re.sub(r'from pynput import keyboard', r'from pynput import keyboard  # type: ignore', content)

# 7. Add type ignore to rec.discard()
content = re.sub(r'rec\.discard\(\)', r'rec.discard()  # type: ignore', content)

# 8. Add type ignore to rec.stop()
content = re.sub(r'audio_path = rec\.stop\(\)', r'audio_path = rec.stop()  # type: ignore', content)

with open("linux/blitztext/daemon.py", "w") as f:
    f.write(content)

print("Fixed lint errors")
