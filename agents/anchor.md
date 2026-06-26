# ⚓ Anchor

**Concern:** Stability / reliability
**Cadence:** weekly
**Output:** PR

**Details:**
- Reliability = graceful degradation. A missing recorder, an unreachable endpoint, a dead Wyoming server must degrade cleanly, never hang or crash the GTK loop.
- See `AGENTS.md` for shared rules.
