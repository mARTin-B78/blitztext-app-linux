# Security Policy

Blitztext App Linux is experimental software.

It is provided as-is, without warranty, support guarantees, or production-readiness claims.

## Supported Versions

Only the current `main` branch is considered for security fixes.

## Reporting A Vulnerability

Please do not open a public issue with sensitive security details.

Use GitHub private vulnerability reporting for this repository. If private vulnerability reporting is not available yet, open a minimal public issue titled `Security contact request` without technical details.

Do not include API keys, access tokens, private recordings, confidential transcripts, screenshots with sensitive text, or private endpoint URLs in a report.

Include:

- what you found
- how to reproduce it
- what data or system access could be affected
- your suggested fix, if you have one

## Security Notes

- Blitztext types into the focused X11 window through `xdotool` or uses the clipboard, depending on output mode.
- Global hotkeys and synthetic typing are powerful desktop interactions; review the code before using it with sensitive workflows.
- Batch transcription may create temporary audio files during processing; the app attempts to delete them when the workflow ends or is cancelled.
- Remote STT, realtime STT, and rewrite workflows send data to the endpoints you configure.
- The app does not store API keys directly; config entries name environment variables such as `OPENAI_API_KEY`.
- The app does not include a hosted backend.

Do not use this preview for confidential or regulated data without your own review.
