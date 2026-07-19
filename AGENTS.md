# Jules Agents - Shared Rules

This file documents the shared setup, environment rules, and scope discipline for all agents that patrol the Blitztext codebase.

## Environment & Verification

To mirror CI, every agent must start from a working environment. Use the following commands:

```bash
sudo apt-get update && sudo apt-get install -y \
  python3-gi gir1.2-gtk-3.0 gir1.2-appindicator3-0.1 \
  libgirepository1.0-dev libgirepository-2.0-dev pkg-config build-essential \
  libcairo2-dev python3-dev
cd linux
pip install -r requirements.txt && pip install pytest ruff PyGObject
python -m py_compile blitztext/*.py     # syntax gate
PYTHONPATH=. pytest tests               # test gate
ruff check blitztext tests              # quality gate
```

## Scope Discipline

- **One concern, one small PR.** No drive-by refactors.
- **If there's no clear, high-confidence win this run, STOP — don't open a PR.**
- Check existing open PRs/branches first; never duplicate another agent's work.
- Never touch `requirements.txt`, `pyrightconfig.json`, or CI without it being the explicit point of the task.
- Never commit secrets, real audio, transcripts, or private endpoint URLs.
- Bump `linux/blitztext/__init__.py` and add a `CHANGELOG.md` entry for any user-visible change. SemVer rules: fix = patch, feature = minor.

## Journals

Read `.jules/<name>.md` before making changes. Append only critical, codebase-specific learnings. Never append routine logs.
Format:
```markdown
## YYYY-MM-DD — [Title]
**Learning:** ...
**Action:** ...
```

## PR Format

```markdown
Title: "<emoji> <Name>: <one-line change>"
Body:
  💡 What  — the change
  🎯 Why   — the problem it solves
  ⚠️ Risk  — blast radius + how mitigated
  🔬 Verified — exact commands run (py_compile / pytest / ruff / build-deb)
  📎 Scope — files touched; confirm no unrelated changes
```
