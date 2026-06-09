"""In-memory log buffer shown in Settings → Log, mirrored to stderr.

Our own messages go through log(); library logs (faster-whisper, huggingface_hub)
are captured via a logging handler so model download/load progress is visible
instead of an opaque "Loading…".

Each entry stores (timestamp_str, level, message) so the UI can filter by level.
Levels: DEBUG, INFO, WARNING, ERROR  (default: INFO)
"""

from __future__ import annotations

import logging
import sys
import threading
import time
from collections import deque

# Each entry: (time_str, level, message)
_ENTRIES: deque[tuple[str, str, str]] = deque(maxlen=2000)
_LOCK = threading.Lock()

_LEVEL_ORDER = {"DEBUG": 0, "INFO": 1, "WARNING": 2, "ERROR": 3}


def log(msg: str, *, echo: bool = True, level: str = "INFO") -> None:
    level = level.upper()
    ts = time.strftime("%H:%M:%S")
    with _LOCK:
        _ENTRIES.append((ts, level, msg))
    if echo:
        print(f"{ts}  [{level}]  {msg}", file=sys.stderr, flush=True)


def lines(min_level: str = "DEBUG") -> list[str]:
    """Return formatted lines at or above min_level."""
    threshold = _LEVEL_ORDER.get(min_level.upper(), 0)
    with _LOCK:
        entries = list(_ENTRIES)
    result = []
    for ts, lvl, msg in entries:
        if _LEVEL_ORDER.get(lvl, 1) >= threshold:
            prefix = f"[{lvl}] " if lvl not in ("INFO",) else ""
            result.append(f"{ts}  {prefix}{msg}")
    return result


def clear() -> None:
    with _LOCK:
        _ENTRIES.clear()


class _BufferHandler(logging.Handler):
    _PY_TO_LEVEL = {
        logging.DEBUG:   "DEBUG",
        logging.INFO:    "INFO",
        logging.WARNING: "WARNING",
        logging.ERROR:   "ERROR",
        logging.CRITICAL:"ERROR",
    }

    def emit(self, record: logging.LogRecord) -> None:
        try:
            lvl = self._PY_TO_LEVEL.get(record.levelno, "INFO")
            log(self.format(record), echo=False, level=lvl)
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
        lg.setLevel(logging.DEBUG)
