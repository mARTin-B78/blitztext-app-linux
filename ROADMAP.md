# Roadmap

This is a preview roadmap, not a promise.

## Current Scope

- Linux/X11 native dictation app
- GTK control panel and AppIndicator tray
- global hotkeys and modifier input mode
- local batch transcription through `faster-whisper`
- OpenAI-compatible batch STT endpoints
- Riva/NIM realtime STT streaming through WebSocket
- optional rewrite workflows through OpenAI-compatible chat endpoints
- xdotool typing or clipboard paste into the focused window
- Debian package for local Ubuntu/Debian installs
- no hosted Blitztext backend

## Next Useful Work

- Capture and add current Linux screenshots for the control panel, settings, benchmark, and About tab.
- Improve first-run setup for STT engines, microphones, and output mode.
- Add a guided realtime STT streaming test that does not type into the active window.
- Add automated tests around config parsing, routing, quality filters, URL handling, and streaming protocol message generation.
- Improve Wayland support with `wtype` or `ydotool` as alternatives to `xdotool`.
- Add safer clipboard handling and clearer output-mode diagnostics.
- Add a lightweight release checklist for `.deb` builds and source installs.
- Document known-good local LLM and STT server configurations.

## Not In Scope Yet

- Production support.
- Accounts, sync, teams, or hosted infrastructure.
- Claims that the app is offline or privacy-complete by default.
- App Store distribution.
- A polished one-click consumer release.
