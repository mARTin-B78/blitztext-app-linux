# AGENTS.md - Shared rules for Jules agents

## Environment Setup / Verification
Every Jules run must start from a working environment. Mirror the CI environment:

```bash
sudo apt-get update && sudo apt-get install -y \
  python3-gi gir1.2-gtk-3.0 gir1.2-appindicator3-0.1 \
  libgirepository1.0-dev libgirepository-2.0-dev libcairo2-dev python3-dev \
  pkg-config build-essential
cd linux
pip install -r requirements.txt && pip install pytest ruff PyGObject numpy
python -m py_compile blitztext/*.py     # syntax gate
PYTHONPATH=. pytest tests               # test gate
ruff check blitztext tests              # quality gate
```

## Scope discipline
- **One concern, one small PR.** No drive-by refactors (the repo's CONTRIBUTING says so explicitly).
- **If there's no clear, high-confidence win this run, STOP — don't open a PR.**
- Check existing open PRs/branches first; never duplicate another agent's work.
- Never touch `requirements.txt`, `pyrightconfig.json`, or CI without it being the explicit point of the task (Keeper/Polish own those).
- Never commit secrets, real audio, transcripts, or private endpoint URLs.
- Bump `linux/blitztext/__init__.py` + add a `CHANGELOG.md` entry for any user-visible change. SemVer: fix → patch, feature → minor.
- Do not run or commit automated lint fixes on unrelated files. Limit linter targets to explicitly modified files (e.g. `ruff check file1.py`).
- Do not use `gh pr create` directly in the execution environment unless you explicitly install it (`sudo apt-get update && sudo apt-get install -y gh`), but prefer the native `submit` tool where possible.
- Local `pytest` is installed via pipx. If testing fails due to missing modules, install them directly into the pipx environment (e.g., `/home/jules/.local/share/pipx/venvs/pytest/bin/python -m pip install <module>`).

## Journal
Read `.jules/<name>.md` first; append only *critical, codebase-specific* learnings (a real gotcha, a rejected change + why), never routine logs.
Format:
```
## YYYY-MM-DD — [Title]
**Learning:** …
**Action:** …
```

## PR format
```
Title: "<emoji> <Name>: <one-line change>"
Body:
  💡 What  — the change
  🎯 Why   — the problem it solves
  ⚠️ Risk  — blast radius + how mitigated
  🔬 Verified — exact commands run (py_compile / pytest / ruff / build-deb)
  📎 Scope — files touched; confirm no unrelated changes
```
