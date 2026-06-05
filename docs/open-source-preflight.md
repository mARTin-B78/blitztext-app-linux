# Open Source Preflight

Use this checklist before making `blitztext-app-linux` public or cutting a public preview release.

## P0 Before Public

- Run a local source install from `linux/install.sh`.
- Run `linux/.venv/bin/python -m py_compile` across the app package.
- Build a `.deb` with `linux/packaging/build-deb.sh` and install it on a clean Ubuntu/Debian test machine.
- Run a secret scan across the working tree and commit history.
- Confirm there are no private URLs, hosted backend credentials, internal docs, private recordings, or confidential transcripts.
- Confirm old macOS-only claims have been replaced with Linux/X11 wording.
- Confirm the root `LICENSE`, `README.md`, `SECURITY.md`, `CONTRIBUTING.md`, `SUPPORT.md`, and `TRADEMARKS.md` are present.
- Keep the preview status explicit: experimental, no hosted backend, no warranty, no support guarantee.
- Credit the inspiration project: `cmagnussen/blitztext-app`.
- Enable GitHub private vulnerability reporting, secret scanning, and push protection before switching the repo public.
- Enable Dependabot alerts.
- Protect `main` with pull requests, at least one review, and required CI checks.
- Keep GitHub Actions permissions read-only by default.

## P1 Soon After Public

- Decide whether Issues alone are enough or whether Discussions should be enabled for questions.
- Add repository topics such as `linux`, `dictation`, `speech-to-text`, `gtk`, `x11`, `faster-whisper`, `riva`, `nim`, and `openai-compatible`.
- Add current Linux screenshots to `docs/screenshots/`.
- Add a small test layer for config parsing, workflow routing, and streaming URL handling.
- Add release notes for `.deb` artifacts.

## P2 Later

- Add CODEOWNERS if multiple maintainers become active.
- Consider CodeQL once the repo has enough surface area to justify scheduled scans.
- Add Wayland support notes or implementation.
- Add signed release artifacts if the project becomes useful beyond developer previews.
