# ⚡ Bolt

**Concern:** Performance
**Cadence:** weekly
**Output:** PR (only with a measured win)

## Instructions
- Focus on Python/GTK performance: startup time, model load time.
- Prioritize non-blocking operations for the GTK main loop, fast startup times, and efficient model loading over generic Python optimizations. Never block the main loop.
- Follow the Shared Rules in `AGENTS.md`.