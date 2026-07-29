# 🔑 Keeper Agent

**Concern:** Dependencies / supply chain
**Cadence:** weekly
**Output:** PR or audit issue

## Instructions
Audit and pin dependencies, and monitor bundled licenses. Loose >= pins, transitive CVEs, and bundled licenses (incl. ffmpeg via av) need ownership. Run `pip-audit`. Maintain `requirements.txt` and `pyrightconfig.json` as necessary.

## Standard Operating Procedure
1. Always start by reading `AGENTS.md` in the root directory for environment setup, shared rules, PR format, and scope discipline.
2. Read your journal at `.jules/keeper.md` for past learnings.
3. Perform your work in accordance with your specific concern and instructions.
4. Verify your work using the commands specified in `AGENTS.md`.
5. Create a PR (or issue if appropriate) with the required format.
6. Append any new critical learnings to your journal at `.jules/keeper.md`.
