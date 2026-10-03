# Changelog

All notable changes to this project will be documented in this file.

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
