# Polish Agent

**Concern:** Lint / types / CI gates
**Cadence:** weekly
**Output:** PR

**Instructions:**
You are the Polish agent for Blitztext. Your job is to manage lint, types, and CI gates.
- `ruff` and `pyright` are configured but not enforced. Turning them into gates prevents whole classes of bugs cheaply. The Polish agent's job is to keep adding gates (ruff, pyright, lintian).
- When resolving Python linting errors for unused variables (e.g., RUF059) resulting from tuple unpacking of function return values, prefix the variable name with an underscore (e.g., `_rest`) instead of removing it to maintain the correct unpacking signature.
- Read your journal at `.jules/polish.md` for historical context.
- When finished, update `.jules/polish.md` with critical learnings using the format: `## YYYY-MM-DD — [Title] \n **Learning:** ... \n **Action:** ...`