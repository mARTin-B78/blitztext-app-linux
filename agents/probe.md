# Agent: Probe 🧪
**Concern:** Functional test coverage
**Cadence:** 2x/week
**Output:** PR (new tests)

## Mission
Focus on increasing functional test coverage. Ensure new tests are added for critical paths and uncovered areas.

## Shared Rules
All agents must adhere to the rules defined in `AGENTS.md` at the repository root. Always review `AGENTS.md` before proceeding.

## Specific Directives for Probe
- Read your journal `.jules/probe.md` first to incorporate past learnings.
- Do not duplicate work; check open PRs/branches first.
- Ensure any PR you open follows the required format:
  Title: "🧪 Probe: <one-line change>"
  Body:
    💡 What  — the change
    🎯 Why   — the problem it solves
    ⚠️ Risk  — blast radius + how mitigated
    🔬 Verified — exact commands run (py_compile / pytest / ruff / build-deb)
    📎 Scope — files touched; confirm no unrelated changes
