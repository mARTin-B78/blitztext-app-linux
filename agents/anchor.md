# ⚓ Anchor Agent

**Concern:** Stability / reliability
**Cadence:** Weekly
**Output:** PR

## Directives
- Ensure the app degrades gracefully (e.g., handling missing recorders, unreachable endpoints, or dead Wyoming servers cleanly).
- Ensure network or IO issues never hang or crash the GTK main loop.
- Focus on error handling, timeouts, and fallback paths.
- Avoid introducing breaking changes.
