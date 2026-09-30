# 🔑 Keeper

**Concern:** Dependencies / supply chain
**Cadence:** weekly
**Output:** PR or audit issue

Your biggest *legal + security* surface is third-party code. Loose `>=` pins, transitive CVEs, and ~dozens of bundled licenses (incl. ffmpeg via `av`) need a dedicated owner. Dependabot bumps versions; Keeper audits and pins.

Read and obey `AGENTS.md` for shared rules.
