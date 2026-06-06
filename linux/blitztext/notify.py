"""Lightweight desktop feedback via notify-send, with stdout fallback."""

from __future__ import annotations

import shutil
import subprocess
import sys

_HAVE_NOTIFY = shutil.which("notify-send") is not None
_APP = "Blitztext"
# Reuse one notification bubble instead of stacking them.
_REPLACE_ID = "99317"


def notify(title: str, body: str = "", *, urgency: str = "normal", enabled: bool = True,
           transient: bool = True) -> None:
    if enabled and _HAVE_NOTIFY:
        try:
            args = [
                "notify-send",
                "--app-name", _APP,
                "--urgency", urgency,
                "--expire-time", "2500",
                # Replace the previous bubble instead of stacking.
                "--hint", f"string:x-canonical-private-synchronous:{_REPLACE_ID}",
            ]
            if transient:
                # Don't keep it in the notification log / lock screen.
                args += ["--hint", "boolean:transient:true"]
            args += [title, body]
            subprocess.run(args, check=False)
            return
        except OSError:
            pass
    # Always echo to the console too — useful when running in a terminal.
    line = f"[{_APP}] {title}" + (f" — {body}" if body else "")
    print(line, file=sys.stderr, flush=True)
