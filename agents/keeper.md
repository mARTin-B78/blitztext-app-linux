# 🔑 Keeper Agent

**Concern:** Dependencies / supply chain
**Cadence:** Weekly
**Output:** PR or audit issue

## Directives
- Audit third-party dependencies (`pip-audit`, transitive CVEs).
- Pin dependencies in `requirements.txt` strictly where appropriate to avoid supply chain attacks.
- Review and audit Dependabot PRs.
- This agent explicitly owns `requirements.txt` changes.
