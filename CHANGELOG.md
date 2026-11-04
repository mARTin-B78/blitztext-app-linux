# Changelog

All notable changes to this project will be documented in this file.

## [2.03.75] - 2026-11-04

### Fixed
- TTS "no API key" error now explains that session keys are lost on restart and where to re-enter the key (Settings or the launch environment). Test added.

## [2.03.74] - 2026-11-02

### Changed
- Update popup now shows the changelog of all versions since the installed one (fetched from the tagged release) instead of only the one-line release body.
- Linux code (except the settings window) split into smaller helpers to clear SonarQube complexity/duplication findings; no behaviour change.
- Sonar: added sonar-project.properties; GTK UI modules excluded from coverage

### Fixed
- Settings window: saving no longer risks a `TypeError` from a leftover `show_errors` argument on the TTS-engine commit (`_talk_commit`) after the refactor.
- "Thinking..." overlay animation now shows during an LLM rewrite (a mis-placed `as _GLib` in a comment left `_GLib` undefined, so the pulse was silently skipped).
- **Security:** the wakeword pause flag moved from the shared `/tmp/wake_muted` to the per-user `$XDG_RUNTIME_DIR/blitztext-wake_muted` (fallback `~/.cache/blitztext/`, created 0700). Another local user could plant the old file to mute your wakeword, or a symlink in its place. External scripts that touched `/tmp/wake_muted` must use the new path.

## [2.03.73] - 2026-11-01

### Changed
- Version bump to test the in-app updater; no functional change.
- Update check now tells "No update found" / "up to date" apart from "Could not reach GitHub".

## [2.03.72] - 2026-11-01

### Added
- **Single version source:** `linux/pyproject.toml` is now the only place the version is set; `__version__` and `build-deb.sh` read it, and the build aborts if a git tag at HEAD differs.
- **In-app updater:** on tray start (at most once a day, can be turned off in
  Settings > About, "Check for updates automatically") Blitztext asks the GitHub
  releases API for the latest release. If it is newer, a dialog offers
  "Update now" / "Remind me later" / "Skip this version". "Update now" downloads
  `blitztext_<ver>_<arch>.deb`, verifies it against the release's `.sha256`, installs
  it with `pkexec apt install`, then restarts the tray. Settings > About also has a
  "Check for updates" button. `build-deb.sh` now writes
  `dist/blitztext_<ver>_<arch>.deb.sha256` next to the .deb. **Releases must be
  tagged `v<ver>` (e.g. `v2.03.73`) and attach both the .deb and its .sha256**,
  otherwise the updater ignores the release.

### Fixed
- Removed the "API key env (fallback)" field from the LLM and TTS Engines pages
  (and the benchmark TTS field); only the masked, session-only API key field remains.
  Saving never fails on it: an `api_key_env` in an old config that is not a valid
  environment variable name (e.g. a pasted key) is cleared on save, valid names are
  kept. LLM/TTS requests ignore an invalid name instead of raising.

## [2.03.71] - 2026-10-03

### Fixed
- **TTS cut off mid-sentence on long text:** "Speak selected text" now splits
  the selection at paragraph/sentence ends (about 1200 characters per chunk)
  and plays the chunks one after another, so no single request reaches the
  server's generation limit. Sentences are never split.

## [2.03.65] - 2026-08-20

### Fixed
- **Keyboard shortcut state:** Prevent stale Windows/Super-key state from
  accidentally starting dictation when Ctrl is pressed.
- **TTS modifier handling:** Stop forcibly releasing global modifiers during
  clipboard selection, avoiding desynchronization with keyboard listeners.

### Added
- **Keyboard TTS shortcut:** Added a synchronized TTS shortcut field to the
  Keyboard settings page.

## [2.03.64] - 2026-08-19

### Fixed
- **STT test waveform stream:** The test now uses a dedicated microphone level
  capture while recording, avoiding contention with the background settings meter.

## [2.03.63] - 2026-08-19

### Fixed
- **STT microphone feedback:** The live level meter no longer depends on
  NumPy, so the settings waveform works in the packaged installation.

## [2.03.62] - 2026-08-19

### Added
- **STT test waveform:** The STT Engines test now shows live microphone activity
  while the four-second recording is in progress.

## [2.03.61] - 2026-07-07

### Added
- **TTS Engine Extra Payload:** Added a new configuration field ("Extra Payload") in the TTS settings UI to allow custom JSON injection (e.g. `{"app": "Blitztext"}`) for Voice Creator proxy language routing.
- **System Tray TTS Playback:** Added a "🔊 Speak selected text" option to the system tray (AppIndicator) menu, allowing TTS playback without relying on global keyboard shortcuts.
- **Robust Text Extraction:** Replaced hardcoded `xclip` reliance with a robust clipboard getter that seamlessly falls back to `xsel` or `wl-paste` (Wayland support) to prevent silent failures when reading primary selection or clipboard.

### Fixed
- Fixed an `AttributeError` crashing the `talk.play` background thread when accessing `active_tts` instead of `active_talk`.
- Ensured UI dropdowns dynamically fetch available models/voices and gracefully fallback to default strings if proxy doesn't return metadata.
