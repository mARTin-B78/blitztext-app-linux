# Changelog

All notable changes to this project will be documented in this file.

## [2.03.61] - 2026-07-07

### Added
- **TTS Engine Extra Payload:** Added a new configuration field ("Extra Payload") in the TTS settings UI to allow custom JSON injection (e.g. `{"app": "Blitztext"}`) for Voice Creator proxy language routing.
- **System Tray TTS Playback:** Added a "🔊 Speak selected text" option to the system tray (AppIndicator) menu, allowing TTS playback without relying on global keyboard shortcuts.
- **Robust Text Extraction:** Replaced hardcoded `xclip` reliance with a robust clipboard getter that seamlessly falls back to `xsel` or `wl-paste` (Wayland support) to prevent silent failures when reading primary selection or clipboard.

### Fixed
- Fixed an `AttributeError` crashing the `talk.play` background thread when accessing `active_tts` instead of `active_talk`.
- Ensured UI dropdowns dynamically fetch available models/voices and gracefully fallback to default strings if proxy doesn't return metadata.
