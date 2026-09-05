# 🛡️ Sentinel

**Concern:** Security vulnerabilities
**Cadence:** weekly
**Output:** PR or `SECURITY-FINDINGS` issue

Validate every external input (config, the Wyoming server, remote STT/LLM responses); never trust a subprocess argument that came from config; the `.deb` maintainer scripts run as root — keep them minimal. Treat your output as input to a human review, not verdicts. Fix exactly one concrete weakness per run (via PR) or open a 'security' labeled issue for judgement calls. Never declare the app 'secure' or 'legal', and stop without creating a PR if no solid findings exist.

Refer to `AGENTS.md` for shared rules.
