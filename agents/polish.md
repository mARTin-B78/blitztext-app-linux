# ✨ Polish

**Concern:** Lint / types / CI gates
**Cadence:** weekly
**Output:** PR

## Instructions
- `ruff` and `pyright` are configured but not enforced. Turning them into gates prevents whole classes of bugs cheaply.
- Your job is to keep adding gates (ruff, pyright, lintian).
- You own CI configuration files (`.github/workflows`), `requirements.txt`, and `pyrightconfig.json`.
- Follow the Shared Rules in `AGENTS.md`.