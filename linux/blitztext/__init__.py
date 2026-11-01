"""Blitztext for Linux — native dictation daemon.

Press a global hotkey, speak, and the transcribed (optionally LLM-rewritten)
text is typed into whatever text field currently has focus. This is the Linux
counterpart to the macOS Blitztext menu bar app: it runs natively on the host
(not in a container) so it can type into any application via xdotool.
"""



def _version() -> str:
    # Source checkout: pyproject.toml sits next to the package (wins over stale metadata).
    # Installed deb: build-deb.sh generates _version.py; else dist metadata.
    from pathlib import Path
    pp = Path(__file__).resolve().parent.parent / "pyproject.toml"
    try:
        if pp.is_file():
            import tomllib
            return tomllib.loads(pp.read_text())["project"]["version"]
        from ._version import VERSION
        return VERSION
    except Exception:
        pass
    try:
        from importlib.metadata import version
        return version("blitztext")
    except Exception:
        return "0+unknown"


__version__ = _version()
