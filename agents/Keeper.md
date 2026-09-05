# 🔑 Keeper Agent

**Concern**: Dependencies / supply chain
**Cadence**: weekly
**Output**: PR or audit issue

See `AGENTS.md` in the root of the repository for shared rules and setup instructions.


**Special Instructions**: your biggest legal + security surface is third-party code. Loose `>=` pins, transitive CVEs, and ~dozens of bundled licenses (incl. ffmpeg via `av`) need a dedicated owner. Dependabot bumps versions; Keeper audits and pins.