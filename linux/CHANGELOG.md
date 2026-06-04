# Changelog

All notable changes to **Blitztext for Linux** (the native dictation tool in
`linux/`) are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

The version is defined in [`blitztext/__init__.py`](blitztext/__init__.py).

## [Unreleased]

## [1.1.0] - 2026-06-04

### Added
- **Debian package** (`packaging/build-deb.sh`) producing an installable
  `blitztext_<ver>_arm64.deb` with a desktop entry, app icon, and a `blitztext`
  launcher. Installs via the Software app or `apt install ./…deb`. Bundles a
  relocatable venv with all Python deps (no pip/network at install) and declares
  system deps (python3-gi, xdotool, libnotify-bin, a recorder) so they pull in
  automatically. The bundled venv is built on the system `/usr/bin/python3`, so
  the tray works out of the box.

### Notes
- `python3-gi` is already present on a standard Ubuntu GNOME install; the tray
  only seemed unavailable from source when the project venv was built from a
  non-system Python (e.g. conda/miniforge). The `.deb` avoids this entirely.

## [1.0.1] - 2026-06-03

### Changed
- Redesigned the control-panel window: minimal flat layout, Ubuntu font
  throughout, clickable workflow rows with hover (click to record / stop),
  subtle dividers, and text-style Settings/Quit actions. Dropped the monogram
  avatars and per-row buttons in favour of a cleaner, simpler look. The Settings
  window picks up the same font and styling.

## [1.0.0] - 2026-06-03

First release of the Linux port. The upstream project is a macOS-only menu-bar
app (Swift/SwiftUI, CoreML/WhisperKit) that cannot run on Linux or in a
container; this is a native host tool that reproduces the workflow — focus any
text field, press a hotkey, speak, and the (optionally rewritten) text is typed
into that field.

### Added
- **Native dictation engine** (`daemon.py`): global hotkeys via pynput, each
  hotkey toggles record → transcribe → optional rewrite → deliver.
- **Local transcription** via faster-whisper (`transcribe.py`); `device="auto"`
  tries CUDA and falls back to CPU `int8` (CPU-only on this arm64 host).
- **Microphone recording** (`recorder.py`) through pw-record / parecord /
  arecord — 16 kHz mono WAV, no Python audio bindings required.
- **Optional LLM rewrite** (`rewrite.py`) against any OpenAI-compatible endpoint
  (OpenAI, or a local vLLM / llama-swap), configurable per workflow.
- **Typing into the focused window** via xdotool (`paste.py`): `type` directly
  or `paste` through the clipboard; re-activates the target window first.
- **Configurable workflows** (`config.py`) in `~/.config/blitztext/config.toml`,
  with five defaults (Transcribe, Nicer email, Improve text, Calm down, Add
  emojis), per-workflow prompt/model/temperature overrides, and a TOML writer.
- **Control-panel window** (`gui.py`, tkinter): workflow rows with monogram
  avatars, hotkey badges, per-row Record buttons, a live status dot, and a
  Settings window that edits config and can Save & Restart.
- **System-tray mode** (`tray.py`, AppIndicator): macOS-menu-bar-style status
  icon with a menu to trigger each workflow, Show panel, Settings…, and Quit;
  shares one daemon/model/hotkey set with the window. Falls back to the window
  with an install hint when PyGObject is absent.
- **CLI** (`__main__.py`): `tray` (default), `gui`, `run`, `transcribe`,
  `config-path`, and `--version`.
- **Packaging**: `install.sh` (venv with `--system-site-packages`),
  `requirements.txt`, and a `blitztext.service` systemd user unit.

### Notes
- Targets an **X11** session (uses xdotool); Wayland would need ydotool/wtype.
- System tray requires a one-time `sudo apt install python3-gi` (the GTK /
  AppIndicator typelibs and GNOME `ubuntu-appindicators` extension are already
  present on the target host).

[Unreleased]: https://github.com/mARTin-B78/blitztext-app/compare/v1.1.0...HEAD
[1.1.0]: https://github.com/mARTin-B78/blitztext-app/compare/v1.0.1...v1.1.0
[1.0.1]: https://github.com/mARTin-B78/blitztext-app/compare/v1.0.0...v1.0.1
[1.0.0]: https://github.com/mARTin-B78/blitztext-app/releases/tag/v1.0.0
