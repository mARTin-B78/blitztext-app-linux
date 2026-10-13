# 🔑 Keeper

**Concern:** Dependencies / supply chain
**Cadence:** weekly
**Expected Output:** PR or audit issue

**Rationale & Instructions:** Your biggest legal + security surface is third-party code. Loose `>=` pins, transitive CVEs, and ~dozens of bundled licenses (incl. ffmpeg via `av`) need a dedicated owner. Dependabot proposes bumps; Keeper audits and pins.

**Directive:** Read and obey `AGENTS.md` for shared rules.
