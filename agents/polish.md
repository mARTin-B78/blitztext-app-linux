# ✨ Polish

**Concern:** Lint / types / CI gates
**Cadence:** weekly
**Output:** PR

## Directives

- **Automated gates.** `py_compile`, `pytest`, `ruff`, secret-scan run in CI on every PR. Agents must pass them; the *Polish* agent's job is to keep adding gates (ruff, pyright, lintian).
- `ruff` and `pyright` are configured but not enforced. Turning them into gates prevents whole classes of bugs cheaply.

---

**Before you start:** Read the shared rules in `AGENTS.md` and your journal in `.jules/polish.md`.
