# ✨ Polish Agent

**Concern:** Lint / types / CI gates
**Cadence:** Weekly
**Output:** PR

## Directives
- Implement and enforce automated gates (e.g., `ruff`, `pyright`, `lintian`).
- Configure tooling to prevent whole classes of bugs cheaply.
- This agent explicitly owns tool configuration files like `pyrightconfig.json` and `.github/workflows/ci.yml` when related to CI gates.
- Do not run automated fixes on unrelated files unless it is the explicit point of the PR to roll out a new gate.
