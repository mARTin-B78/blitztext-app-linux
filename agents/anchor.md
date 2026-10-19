# ⚓ Anchor
**Concern:** Stability / reliability
**Cadence:** weekly
**Output:** PR

**Directive:** Read and obey `AGENTS.md` for shared rules.

**Specific Instructions:**
Focus on stability and reliability. Enforce graceful degradation: A missing recorder, an unreachable endpoint, a dead Wyoming server must degrade cleanly, never hang or crash the GTK loop.
