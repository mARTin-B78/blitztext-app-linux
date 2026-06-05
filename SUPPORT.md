# Support

Blitztext App Linux is an experimental preview. There is no service-level agreement, paid support channel, or guarantee that issues will be fixed.

## Before Asking For Help

- Make sure you can install from `linux/install.sh` or build the `.deb` with `linux/packaging/build-deb.sh`.
- Confirm you are running an X11 session if you expect automatic typing through `xdotool`.
- Check that your microphone works and that the Settings input meter moves.
- Check that your selected STT engine is the right type: `local`, `openai`, or `riva_realtime`.
- For rewrite workflows, confirm your OpenAI-compatible LLM endpoint and API key environment variable.
- Read [docs/privacy.md](docs/privacy.md) before testing with sensitive content.

## Where To Ask

Use GitHub Issues for reproducible bugs and focused feature ideas.

Please do not post:

- API keys
- access tokens
- private endpoint URLs
- private audio recordings
- confidential transcripts
- screenshots that show sensitive content

For security-sensitive reports, follow [SECURITY.md](SECURITY.md) instead of opening a public issue.
