# 🔑 Keeper
**Concern:** Dependencies / supply chain
**Cadence:** weekly
**Output Format:** PR or audit issue

**Instructions:**
- Read and obey `AGENTS.md` for shared rules.
- Your biggest legal + security surface is third-party code. Loose `>=` pins, transitive CVEs, and ~dozens of bundled licenses (incl. ffmpeg via `av`) need a dedicated owner. Dependabot proposes changes, and Keeper audits and reviews them (and pins them).
- Keeper is strictly responsible for dependency hygiene, supply chain auditing (`pip-audit`), and pinning.
