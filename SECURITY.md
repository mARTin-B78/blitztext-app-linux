# Security Policy

Blitztext macOS Preview is experimental software.

It is provided as-is, without warranty, support guarantees, or production-readiness claims.

## Supported Versions

Only the current `main` branch is considered for security fixes.

## Reporting A Vulnerability

Please do not open a public issue with sensitive security details.

Use GitHub private vulnerability reporting for this repository. Maintainers should enable it before making the repository public.

If private vulnerability reporting is not available yet, open a minimal public issue titled `Security contact request` without technical details.

Do not include OpenAI API keys, access tokens, private recordings, or confidential transcripts in a report.

Include:

- what you found
- how to reproduce it
- what data or system access could be affected
- your suggested fix, if you have one

## Security Notes

- The app sends audio and text directly to OpenAI when you use the remote workflows.
- Your OpenAI API key is stored in the user's macOS Keychain.
- Temporary audio files may exist briefly during processing.
- Accessibility permission allows the app to paste text into the current app.
- The app currently runs **without** the macOS App Sandbox. This is a deliberate trade-off for the preview: the menubar workflow needs Accessibility-based paste into arbitrary frontmost apps, system-wide hotkeys, and Application Support paths for local WhisperKit models, all of which are awkward or impossible inside a strict sandbox. Hardened Runtime is enabled, and the entitlements are limited to microphone input and outbound network access. Reintroducing the sandbox is on the roadmap once these flows are reworked.

Do not use this preview for confidential or regulated data without your own review.
