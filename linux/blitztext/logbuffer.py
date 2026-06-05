"""In-memory log buffer shown in Settings → Log, mirrored to stderr.

Our own messages go through log(); library logs (faster-whisper, huggingface_hub)
are captured via a logging handler so model download/load progress is visible
instead of an opaque "Loading…".
"""

from __future__ import annotations

import logging
import sys
import threading
import time
from collections import deque

_LINES: deque[str] = deque(maxlen=2000)
_LOCK = threading.Lock()


def log(msg: str, *, echo: bool = True) -> None:
    line = f"{time.strftime('%H:%M:%S')}  {msg}"
    with _LOCK:
        _LINES.append(line)
    if echo:
        print(line, file=sys.stderr, flush=True)


def lines() -> list[str]:
    with _LOCK:
        return list(_LINES)


def clear() -> None:
    with _LOCK:
        _LINES.clear()


class _BufferHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        try:
            log(self.format(record), echo=False)
        except Exception:  # noqa: BLE001 - never let logging break the app
            pass


_installed = False


def install_logging() -> None:
    """Capture library log records into the buffer (once)."""
    global _installed
    if _installed:
        return
    _installed = True
    handler = _BufferHandler()
    handler.setFormatter(logging.Formatter("%(name)s: %(message)s"))
    for name in ("faster_whisper", "huggingface_hub", "blitztext"):
        lg = logging.getLogger(name)
        lg.addHandler(handler)
        lg.setLevel(logging.INFO)
