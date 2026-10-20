# ⚡ Bolt
**Concern:** Performance
**Cadence:** weekly
**Output:** PR (only with a measured win)

**Directive:** Read and obey `AGENTS.md` for shared rules.

**Rationale:** Re-tailored to Python/GTK (startup, model load, never block the main loop) instead of React/pnpm. Prioritize non-blocking operations for the GTK main loop, fast startup times, and efficient model loading over generic Python optimizations.
