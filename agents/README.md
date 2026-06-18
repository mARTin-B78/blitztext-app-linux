# Jules agent library — Blitztext for Linux

A roster of small, single-purpose [Jules](https://jules.google.com) agents that patrol this codebase on a schedule. Each agent owns **one concern**, makes **one small, reviewable change per run** (or opens an issue/report when a change isn't appropriate), and **must leave CI green**.

The prompts live in this directory (`agents/`). Paste one into a Jules scheduled task, or point Jules at the file. Journals live in `.jules/<name>.md` (the agent maintains its own).

---

## What "stable, secure, reliable, legal" actually takes

No single agent makes software trustworthy — these principles do, and the roster is built to enforce them:

- **Shift left + small PRs.** Catch issues in review, not production. Every change is small enough for a human to actually read.
- **Automated gates.** `py_compile`, `pytest`, `ruff`, secret-scan run in CI on every PR (see `.github/workflows/ci.yml`). Agents must pass them; the *Polish* agent's job is to keep adding gates (ruff, pyright, lintian).
- **Defense in depth + least privilege.** Validate every external input (config, the Wyoming server, remote STT/LLM responses); never trust a subprocess argument that came from config; the `.deb` maintainer scripts run as root — keep them minimal.
- **Reproducible, verifiable builds.** The installer is tested on a clean VM every cycle, not assumed to work.
- **Dependency hygiene.** Pin, audit (`pip-audit`), and know every transitive license. Dependabot proposes; *Keeper* audits and reviews.
- **Privacy by design.** This app handles voice and transcripts — treat them as sensitive: temp-only audio, no transcript logging, keys from env only, remote endpoints honestly disclosed.
- **License + IP compliance with attribution.** Bundled deps ship their notices; trademarks and upstream credit (cmagnussen/blitztext-app) stay intact.
- **Humans decide the hard calls.** Security and legal agents *flag and recommend* — a person (or a lawyer, for patents/licensing) signs off. The agents never claim something is "secure" or "legal."
- **Reliability = graceful degradation.** A missing recorder, an unreachable endpoint, a dead Wyoming server must degrade cleanly, never hang or crash the GTK loop.
- **Traceability.** SemVer + a CHANGELOG entry for every user-visible change.

---

## The roster

| # | Agent | Concern | Cadence | Output |
|---|-------|---------|---------|--------|
| 1 | 🛡️ **Sentinel** | Security vulnerabilities | weekly | PR or `SECURITY-FINDINGS` issue |
| 2 | 🦅 **Hawk** | Correctness bugs | 2×/week | PR (fix + regression test) |
| 3 | ⚓ **Anchor** | Stability / reliability | weekly | PR |
| 4 | ⚖️ **Justice** | Licenses, trademarks, patents | monthly | report PR / issue (no legal advice) |
| 5 | 🧪 **Probe** | Functional test coverage | 2×/week | PR (new tests) |
| 6 | 📖 **Scribe** | Documentation accuracy | weekly | PR |
| 7 | 📦 **Forge** | Installer / packaging | weekly | PR |
| 8 | 🔑 **Keeper** | Dependencies / supply chain | weekly | PR or audit issue |
| 9 | 🕵️ **Warden** | Privacy / data handling | monthly | PR or issue |
| 10 | ✨ **Polish** | Lint / types / CI gates | weekly | PR |
| 11 | ⚡ **Bolt** | Performance | weekly | PR (only with a measured win) |

---

## Scheduling & anti-collision

Agents that edit code will conflict if they run together. Suggested weekly spread (so PRs land one-at-a-time and stay reviewable):

- **Mon** Hawk · **Tue** Probe + Scribe · **Wed** Sentinel · **Thu** Anchor + Forge · **Fri** Polish + Keeper · **Bolt** weekend.
- **Monthly:** Justice (1st), Warden (15th).

Keep a **human merge gate** on every PR — these agents propose, you dispose. Treat Sentinel/Justice/Warden output as *input to a human review*, not verdicts.