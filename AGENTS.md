# Shared Rules for Jules Agents

Every agent operating in this repository must obey the following rules.

## Environment / Verify

Mirror CI (`.github/workflows/ci.yml`) to ensure your environment is set up correctly:

```bash
sudo apt-get update && sudo apt-get install -y \
  python3-gi gir1.2-gtk-3.0 gir1.2-appindicator3-0.1 \
  libgirepository1.0-dev libcairo2-dev python3-dev
cd linux
pip install -r requirements.txt && pip install pytest ruff PyGObject
python -m py_compile blitztext/*.py     # syntax gate
PYTHONPATH=. pytest tests               # test gate
ruff check blitztext tests              # quality gate
```

> **Note:** If the default `python` encounters missing module errors during testing, use the explicit pyenv path (e.g. `/home/jules/.pyenv/versions/3.12.13/bin/python3.12 -m pytest`).

## Scope Discipline

- **One concern, one small PR.** No drive-by refactors (the repo's CONTRIBUTING says so explicitly).
- **If there's no clear, high-confidence win this run, STOP — don't open a PR.**
- Check existing open PRs/branches first; never duplicate another agent's work.
- Never touch `requirements.txt`, `pyrightconfig.json`, or CI configurations without it being the explicit point of the task (Keeper/Polish own those).
- Never commit secrets, real audio, transcripts, or private endpoint URLs (the CI secret scan will fail you anyway).
- Bump `linux/blitztext/__init__.py` and add a `CHANGELOG.md` entry for any user-visible change. SemVer: fix → patch, feature → minor.

## Journal

Read `.jules/<name>.md` first; append only *critical, codebase-specific* learnings (a real gotcha, a rejected change + why), never routine logs.

Format:
```markdown
## YYYY-MM-DD — [Title]
**Learning:** ...
**Action:** ...
```

## PR Format

Ensure your PR follows this format strictly:

```markdown
Title: "<emoji> <Name>: <one-line change>"
Body:
  💡 What  — the change
  🎯 Why   — the problem it solves
  ⚠️ Risk  — blast radius + how mitigated
  🔬 Verified — exact commands run (py_compile / pytest / ruff / build-deb)
  📎 Scope — files touched; confirm no unrelated changes
```

## Security & Secrets Workaround

The CI secret scan uses `.github/secret-scan-patterns.txt` and aggressively matches strings like `OPENAI_API_KEY=`.
To prevent false positives:
- Avoid using exact assignment strings like `OPENAI_API_KEY=` or `OPENAI_API_KEY =` in documentation or setup scripts.
- Rephrase instructions instead of modifying the CI pattern file.
