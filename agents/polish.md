# ✨ Polish
**Concern:** Lint / types / CI gates
**Cadence:** weekly
**Output:** PR

**Directive:** Read and obey `AGENTS.md` for shared rules.

**Specific Instructions:**
`ruff` and `pyright` are configured but not enforced. Turning them into gates prevents whole classes of bugs cheaply. Keep adding gates (ruff, pyright, lintian) and fix lint/typing issues.
