# Jules Agents Shared Rules

This file defines the shared rules and environment setup for all Jules agents patrolling the Blitztext codebase.

## Environment / Verify

Mirror CI (`.github/workflows/ci.yml`). Before starting your task, set up the environment and run these gates locally from the `linux/` directory:

```bash
sudo apt-get update && sudo apt-get install -y \
  python3-gi gir1.2-gtk-3.0 gir1.2-appindicator3-0.1 \
  libgirepository1.0-dev libgirepository-2.0-dev libcairo2-dev python3-dev build-essential pkg-config
cd linux
pip install -r requirements.txt && pip install pytest ruff PyGObject numpy
python -m py_compile blitztext/*.py     # syntax gate
PYTHONPATH=. pytest tests               # test gate
ruff check blitztext tests              # quality gate
```

> **Note:** Local `pytest` may be installed via pipx. If testing fails due to missing modules, install them directly into the pipx environment using `/home/jules/.local/share/pipx/venvs/pytest/bin/python -m pip install <module>`, or ensure you explicitly call the pyenv Python executable containing your requirements (e.g., `/home/jules/.pyenv/versions/3.12.13/bin/python3.12 -m pytest tests`).

## Scope discipline
- **One concern, one small PR.** No drive-by refactors.
- **If there's no clear, high-confidence win this run, STOP — don't open a PR.**
- Check existing open PRs/branches first; never duplicate another agent's work.
- Never touch `requirements.txt`, `pyrightconfig.json`, or CI configurations unless it is the explicit purpose of your task (e.g., Keeper/Polish).
- Never commit secrets, real audio, transcripts, or private endpoint URLs. (The CI secret scan actively checks for these).
- To prevent false positives in CI secret scanning, avoid using exact assignment strings like `OPENAI_API_KEY=` or `OPENAI_API_KEY =` in documentation or setup scripts. Rephrase instead.
- Bump `linux/blitztext/__init__.py` and add a `CHANGELOG.md` entry for any user-visible change. SemVer: fix → patch, feature → minor.

## Journal
Read `.jules/<name>.md` first; append only *critical, codebase-specific* learnings (a real gotcha, a rejected change + why), never routine logs.
Format:
```
## YYYY-MM-DD — [Title]
**Learning:** …
**Action:** …
```

## PR format
PRs must strictly follow this format:
```
Title: "<emoji> <Name>: <one-line change>"
Body:
  💡 What  — the change
  🎯 Why   — the problem it solves
  ⚠️ Risk  — blast radius + how mitigated
  🔬 Verified — exact commands run (py_compile / pytest / ruff / build-deb)
  📎 Scope — files touched; confirm no unrelated changes
```
