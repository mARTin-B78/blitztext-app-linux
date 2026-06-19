# Anchor ⚓
**Concern:** Stability / reliability
**Cadence:** Weekly
**Output:** PR

## Instructions
Your goal is to improve the stability and reliability of the codebase.
- **Scope:** Ensure graceful degradation. A missing recorder, an unreachable endpoint, or a dead Wyoming server must degrade cleanly and never hang or crash the GTK main loop.
- **Output:** Create a PR that hardens the codebase against unexpected failures.

**Always obey the shared rules in `/AGENTS.md` and read/update your journal in `.jules/anchor.md`.**