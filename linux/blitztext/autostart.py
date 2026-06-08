"""Launch-on-login via a freedesktop autostart entry.

Writes ~/.config/autostart/blitztext.desktop so the tray starts with the GNOME
session. No root needed.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

_AUTOSTART_DIR = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "autostart"
_ENTRY = _AUTOSTART_DIR / "blitztext.desktop"


def _exec_command() -> str:
    """Launch the *currently running* copy on login.

    If we're running from a source checkout (not the installed /opt copy or a
    site-packages install), launch that exact source with PYTHONPATH so edits
    stay live. Otherwise prefer the installed `blitztext` launcher.
    """
    import blitztext

    pkg_parent = str(Path(blitztext.__file__).resolve().parent.parent)
    from_source = not pkg_parent.startswith("/opt/") and "site-packages" not in pkg_parent
    if from_source:
        return f"env PYTHONPATH={pkg_parent} {sys.executable} -m blitztext tray"
    launcher = shutil.which("blitztext")
    if launcher:
        return f"{launcher} tray"
    return f"{sys.executable} -m blitztext tray"


def is_enabled() -> bool:
    return _ENTRY.exists()


def set_enabled(enabled: bool) -> None:
    if not enabled:
        _ENTRY.unlink(missing_ok=True)
        return
    _AUTOSTART_DIR.mkdir(parents=True, exist_ok=True)
    _ENTRY.write_text(
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Name=Blitztext\n"
        f"Exec={_exec_command()}\n"
        "Icon=blitztext\n"
        "Terminal=false\n"
        "X-GNOME-Autostart-enabled=true\n"
        "X-GNOME-Autostart-Delay=12\n",
        encoding="utf-8",
    )
