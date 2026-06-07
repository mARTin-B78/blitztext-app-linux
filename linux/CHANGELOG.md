# Changelog

All notable changes to **Blitztext for Linux** (the native dictation tool in
`linux/`) are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

The version is defined in [`blitztext/__init__.py`](blitztext/__init__.py).

## [Unreleased]

## [1.5.0] - 2026-06-07

### Added
- **On-screen dictation overlay** (Settings → General → "Visual overlay", or
  `[general] overlay_enabled`, default on): the moment recording starts — by
  hotkey **or** wakeword — a translucent bubble appears at the cursor showing a
  pulsing **microphone**, a **live waveform** of your mic level, and the
  **recognised text** (word-by-word with a realtime streaming STT engine, or the
  final result as a brief confirmation otherwise). Its tail points at where the
  text will land: it follows the **text caret** when the focused app exposes it
  over accessibility (AT-SPI), otherwise the **mouse pointer**, otherwise a
  screen corner — tune via `[general] overlay_anchor = "caret" | "pointer" |
  "corner"`. The window is click-through and never takes focus, and it finally
  gives **hands-free wakeword sessions** visible feedback (their notifications
  are suppressed by design). X11 only; falls back to a corner where the cursor
  can't be located.

### Changed
- **Presets are speakable by name**: voice routing now matches a preset's *name*
  as an implicit keyword, so a preset works by voice even with no keywords
  configured (e.g. just say "nicer email …"). Explicit keywords still take
  precedence, and preset names also bias the STT for better recognition.
- **General settings switches** moved to the far right of each row, each with an
  inline description so it's clear what the toggle does without hovering.
- **About**: added a "Copyright: 2026 mARTin Bierschenk - Design" line.

## [1.4.0] - 2026-06-07

### Added
- **"Announce matched preset" notification** (Settings → General, or
  `[general] notify_routing`, default on): after a voice command, a notification
  shows which preset and spoken keyword matched — **shown even for hands-free
  wakeword sessions**, so you can see what you triggered. It only fires on a real
  match, so it never spams when nothing is said.
- **Per-preset emoji icon** (Presets → "Icon (emoji)"): give each preset a
  distinct emoji, shown in the matched-preset notification so you can tell at a
  glance which fired.

### Fixed
- **Voice-routing default went to a rewrite**: when no `[routing] default` preset
  is set, the no-keyword fallback used the *first* preset — which, if that happened
  to be an LLM rewrite (e.g. "Improve text"), sent every unrouted wakeword command
  to the language model (and failed when the LLM was down). The fallback now
  prefers a `transcribe` preset, so the default action is plain transcription.

## [1.3.0] - 2026-06-07

### Added
- **Pause wakeword (tray)**: a reversible "Pause wakeword" toggle appears in the
  system-tray menu when the wakeword is enabled. It pauses/resumes hands-free
  detection by toggling the `/tmp/wake_muted` flag (external scripts may toggle
  the same file).
- **"Play audio cues" switch** (Settings → Input → Audio cues, or
  `[sounds] enabled`): on/off for the **manual** (keyboard/hotkey) start/stop
  chimes. Defaults to on. The hands-free wakeword sounds are independent of it.
- **Configurable wakeword auto-stop silence** (Settings → Input → Hands-free →
  "Silence to stop (s)", or `[wakeword] silence_seconds`): end a hands-free
  recording this many seconds after you stop speaking. Defaults to `2.0`
  (previously hard-coded to 2.5 s).

### Fixed
- **Wakeword sounds silenced by the manual cue switch**: the "Play audio cues"
  master switch wrongly muted the hands-free *Sound: detected/captured* cues too.
  Wakeword cues are now independent — they play whenever a file is set and stay
  silent when cleared (no surprise system-chime fallback), regardless of the
  manual switch.
- **PortAudio/ALSA teardown noise**: the level meter no longer leaks
  `pthread_join ... failed` / `PaUnixThread_Terminate ... failed` lines to the
  terminal when a clip ends — that C-library chatter (written straight to fd 2)
  is now suppressed around the stream open/close.
- **Wakeword stuck muted**: a leftover `/tmp/wake_muted` flag silently disabled
  detection with no in-app way to clear it. The state is now exposed and
  reversible from the tray, so a stale flag no longer kills hands-free use. The
  daemon also logs a clear `Starting PAUSED` warning when it boots muted.
- **Away-from-keyboard "Busy" storm**: a wakeword hit arriving while the previous
  clip was still transcribing went through `toggle()` and popped a "Busy"
  notification. Wakeword triggers now go straight to `start_dictation()`, so a
  busy/not-ready state is ignored silently instead.
- **Quiet hands-free errors**: transcription/rewrite failures during a
  wakeword-triggered session no longer raise critical desktop notifications —
  they are logged instead, keeping background sessions silent.
- **Notification storm / lock-screen pile-up**: desktop notifications are now
  sent as transient with a short expiry and reuse a single bubble, so they no
  longer stack in the notification log or persist on the lock screen.
- **Quiet hands-free sessions**: per-dictation notifications are suppressed for
  wakeword-triggered sessions (audio cues are used instead).

## [1.2.0] - 2026-06-05

### Added
- **Wyoming Wakeword Support**: Complete hands-free integration via Wyoming protocol (e.g., openWakeWord), with live configuration testing and model fetching in the UI.
- **ATK Screen Reader Accessibility**: Fully mapped GTK labels, inputs, tooltips, and properties to the ATK bridge, enabling seamless navigation for blind users via screen readers like Orca.
- **Drag-and-Drop Workflow Ordering**: Workflows in the main tray menu can now be reordered via native drag-and-drop.
- **Voice Activity Detection (VAD) Auto-Stop**: Dictation now automatically stops after detecting 2.5 seconds of silence, removing the need to manually click Stop.
- **Audio Feedback**: Added audible start/stop/cancel chimes mapping to system-native alert sounds.
- **Benchmark Autocomplete**: The Benchmark UI automatically fills in the reference `.txt` transcript if it matches the selected audio file.
- **Realtime STT streaming mode**: new `mode = "stream"` workflow support and a
  `riva_realtime` STT engine for Riva/NIM WebSocket transcription, including a
  Settings shortcut for Nemotron ASR Streaming on `http://127.0.0.1:8006/v1`.
- **Settings About tab** with the app version, source link, changelog, and
  license text.
- **STT & LLM engine manager**: add, rename, and delete engine presets, each
  with an online/offline status dot, a per-engine type (local/cloud), and a
  **searchable model dropdown** populated from the server's `/models` (with a
  reload button). Local Whisper device/precision now live with the STT engine.
- **Benchmark tab**: run a reference clip through every STT engine and compare
  **time**, **case-sensitive accuracy** (WER), and a **CPU/GPU/remote device**
  column, with the fastest and most accurate highlighted.
- **Custom audio cues**: pick your own WAV files to play when recording starts
  and stops (covers stop+paste, stop+paste+Enter, and silence auto-stop), each
  with play-test and clear-to-default buttons. Built-in system sounds otherwise.
- **Settings Log tab**: a live activity log (model load/download, transcriptions,
  errors) with Copy and Clear, so a long "Loading…" is no longer opaque.
- **Per-tab info boxes** and expanded **tooltips** across Settings, written in
  plain language and exposed to screen readers (ATK) — for non-technical and
  blind users (barrierefrei).
- **Click-to-bind hotkeys**: a *Set* button captures the next keypress (including
  modifier-only chords like Ctrl+Win) into any hotkey field.

### Changed
- **GUI rebuilt in GTK 3** (replacing tkinter): a native GNOME panel unified with
  the tray, with the Ubuntu font and a dropdown+editor pattern in Settings.
- **Voice-keyword routing** and a **modifier hotkey scheme** (Ctrl+Win start,
  Ctrl stop+paste, Alt stop+paste+Enter, Esc cancel) replace per-preset combos as
  the default way to dictate.
- **Quality gate** rejects silent/too-short clips and stock Whisper
  hallucinations before they reach the screen.

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

[Unreleased]: https://github.com/mARTin-B78/blitztext-app-linux/compare/v1.5.0...HEAD
[1.5.0]: https://github.com/mARTin-B78/blitztext-app-linux/compare/v1.4.0...v1.5.0
[1.1.0]: https://github.com/mARTin-B78/blitztext-app-linux/compare/v1.0.1...v1.1.0
[1.0.1]: https://github.com/mARTin-B78/blitztext-app-linux/compare/v1.0.0...v1.0.1
[1.0.0]: https://github.com/mARTin-B78/blitztext-app-linux/releases/tag/v1.0.0
