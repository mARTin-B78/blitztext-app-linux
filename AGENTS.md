# Jules agent library — Blitztext for Linux

A roster of small, single-purpose Jules agents that patrol this codebase on a schedule. Each agent owns **one concern**, makes **one small, reviewable change per run** (or opens an issue/report when a change isn't appropriate), and **must leave CI green**.

## Shared rules (every agent obeys these)

**Environment / verify** — mirror CI (`.github/workflows/ci.yml`):

```bash
sudo apt-get update && sudo apt-get install -y \
  python3-gi gir1.2-gtk-3.0 gir1.2-appindicator3-0.1 \
  libgirepository1.0-dev libgirepository-2.0-dev libcairo2-dev python3-dev pkg-config build-essential
cd linux
pip install -r requirements.txt && pip install pytest ruff PyGObject
python -m py_compile blitztext/*.py     # syntax gate
PYTHONPATH=. pytest tests               # test gate
ruff check blitztext tests              # quality gate
```

**Scope discipline**
- **One concern, one small PR.** No drive-by refactors (the repo's CONTRIBUTING says so explicitly).
- **If there's no clear, high-confidence win this run, STOP — don't open a PR.**
- Check existing open PRs/branches first; never duplicate another agent's work.
- Never touch `requirements.txt`, `pyrightconfig.json`, or CI without it being the explicit point of the task.
- Never commit secrets, real audio, transcripts, or private endpoint URLs.
- Bump `linux/blitztext/__init__.py` + add a `CHANGELOG.md` entry for any user-visible change. SemVer: fix → patch, feature → minor.

**Journal** — read `.jules/<name>.md` first; append only *critical, codebase-specific* learnings. Format:
```
## YYYY-MM-DD — [Title]
**Learning:** …
**Action:** …
```

**PR format**
```
Title: "<emoji> <Name>: <one-line change>"
Body:
  💡 What  — the change
  🎯 Why   — the problem it solves
  ⚠️ Risk  — blast radius + how mitigated
  🔬 Verified — exact commands run (py_compile / pytest / ruff / build-deb)
  📎 Scope — files touched; confirm no unrelated changes
```
