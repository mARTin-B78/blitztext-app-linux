"""CLI entrypoint: `python -m blitztext [run|transcribe|config-path]`."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .config import CONFIG_PATH, ensure_default, load


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="blitztext", description="Native dictation for Linux.")
    parser.add_argument("--version", action="version", version=f"blitztext {__version__}")
    sub = parser.add_subparsers(dest="cmd")

    sub.add_parser("tray", help="Run in the system tray with a workflow menu (default).")
    sub.add_parser("gui", help="Open the control panel window.")
    sub.add_parser("run", help="Start the headless hotkey daemon (no window/tray).")
    sub.add_parser("config-path", help="Print the config file path and exit.")
    p_tx = sub.add_parser("transcribe", help="Transcribe a WAV file and print the text (no hotkeys).")
    p_tx.add_argument("audio", type=Path)

    args = parser.parse_args(argv)
    cmd = args.cmd or "tray"

    if cmd == "config-path":
        print(ensure_default(CONFIG_PATH))
        return 0

    if cmd in ("gui", "tray"):
        ensure_default(CONFIG_PATH)
        from .gui import run_gui

        return run_gui(tray_mode=(cmd == "tray"))

    cfg = load()

    if cmd == "transcribe":
        from .transcribe import Transcriber

        tx = Transcriber(cfg.model, cfg.device, cfg.compute_type, cfg.beam_size)
        print(tx.transcribe(args.audio, language=cfg.language))
        return 0

    # cmd == "run"
    from .daemon import Daemon

    try:
        Daemon(cfg).run()
    except KeyboardInterrupt:
        print("\n[blitztext] stopped.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
