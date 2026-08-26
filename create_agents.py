import os

agents = [
    ("sentinel", "🛡️ Sentinel", "Security vulnerabilities", "weekly", "PR or `SECURITY-FINDINGS` issue"),
    ("hawk", "🦅 Hawk", "Correctness bugs", "2×/week", "PR (fix + regression test)"),
    ("anchor", "⚓ Anchor", "Stability / reliability", "weekly", "PR"),
    ("justice", "⚖️ Justice", "Licenses, trademarks, patents", "monthly", "report PR / issue (no legal advice)"),
    ("probe", "🧪 Probe", "Functional test coverage", "2×/week", "PR (new tests)"),
    ("scribe", "📖 Scribe", "Documentation accuracy", "weekly", "PR"),
    ("forge", "📦 Forge", "Installer / packaging", "weekly", "PR"),
    ("keeper", "🔑 Keeper", "Dependencies / supply chain", "weekly", "PR or audit issue"),
    ("warden", "🕵️ Warden", "Privacy / data handling", "monthly", "PR or issue"),
    ("polish", "✨ Polish", "Lint / types / CI gates", "weekly", "PR"),
    ("bolt", "⚡ Bolt", "Performance", "weekly", "PR (only with a measured win)")
]

os.makedirs("agents", exist_ok=True)
os.makedirs(".jules", exist_ok=True)

for slug, name, concern, cadence, output in agents:
    prompt = f"""# {name}

You are the {name.split()[1]} agent.
Your primary concern is: **{concern}**.
Cadence: {cadence}
Expected Output: {output}

## Instructions
- You patrol this codebase to address your specific concern.
- You must make **one small, reviewable change per run** (or open an issue/report when a change isn't appropriate).
- You must leave CI green.
- Read `AGENTS.md` for shared rules, environment setup, and PR formatting.
- Read and maintain your journal in `.jules/{slug}.md`.
- Never duplicate another agent's work. Check existing PRs/issues.
"""
    with open(f"agents/{slug}.md", "w") as f:
        f.write(prompt)

    with open(f".jules/{slug}.md", "w") as f:
        f.write(f"# {name} Journal\n")

print("Created agents and journals.")
