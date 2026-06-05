# Contributing

Thanks for taking a look at Blitztext App Linux.

This repository is intentionally a preview. Contributions should make it easier to learn from, build, fork, test, or safely extend.

## Inspiration

This Linux app is inspired by [cmagnussen/blitztext-app](https://github.com/cmagnussen/blitztext-app). Please keep that credit intact when changing project-facing docs.

## Good First Contributions

- improve Linux setup instructions
- add current Linux screenshots
- fix confusing UI text
- improve error messages
- add tests around config parsing, routing, quality filters, and streaming URL handling
- document known-good STT or LLM engine configs
- simplify packaging and first-run setup

## Before Opening A Pull Request

Please include:

- what changed
- why it changed
- how you tested it
- whether you used AI-assisted coding tools

Keep changes small when possible. Avoid unrelated cleanup in the same PR.

## Local Build

```bash
cd linux
./install.sh
.venv/bin/python -m blitztext gui
```

Package build:

```bash
cd linux
bash packaging/build-deb.sh
```

## Security And Privacy

- Never commit API keys, tokens, private audio, confidential transcripts, or private endpoint URLs.
- Avoid adding telemetry, hosted services, or external dependencies without a clear issue first.
- Call out privacy-impacting changes in the pull request description.
- Keep the preview honest: do not describe remote STT or rewrite workflows as offline or local.

## Project Boundaries

This preview currently does not include:

- a hosted backend
- production support
- bundled STT model files
- guaranteed Wayland support
- local text rewriting unless the user configures a local OpenAI-compatible LLM endpoint

Those can be discussed in issues, but please keep PRs focused unless a maintainer agrees on a larger direction first.
