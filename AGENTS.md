# Jules Agent Shared Rules

All Jules agents in this repository must obey the following rules. The scope of this file is the entire repository.

## Environment & Verification

Every agent must start from a working environment. Mirror the CI (`.github/workflows/ci.yml`) by running these setup commands before making or testing changes:

```bash
sudo apt-get update && sudo apt-get install -y \
  python3-gi gir1.2-gtk-3.0 gir1.2-appindicator3-0.1 \
  libgirepository1.0-dev libgirepository-2.0-dev pkg-config build-essential libcairo2-dev python3-dev
cd linux
pip install -r requirements.txt && pip install pytest ruff PyGObject numpy
python -m py_compile blitztext/*.py     # syntax gate
PYTHONPATH=. pytest tests               # test gate
ruff check blitztext tests              # quality gate
```

Local `pytest` should be run within the virtual environment or via pipx if missing modules occur.

## Scope Discipline

- **One concern, one small PR.** No drive-by refactors (the repo's CONTRIBUTING says so explicitly). Do not run automated lint fixes on unrelated files.
- **If there's no clear, high-confidence win this run, STOP — don't open a PR.**
- Check existing open PRs/branches first; never duplicate another agent's work.
- Never touch `requirements.txt`, `pyrightconfig.json`, or CI configurations without it being the explicit point of the task.
- Never commit secrets, real audio, transcripts, or private endpoint URLs. The CI secret scan will fail you anyway.
- Treat voice and transcripts as highly sensitive data: enforce temp-only audio, strictly no transcript logging, and fetch API keys only from the environment.
- Code must degrade gracefully and never hang or crash the GTK main loop.
- Bump `linux/blitztext/__init__.py` and add a `CHANGELOG.md` entry for any user-visible change. SemVer: fix → patch, feature → minor.

## Journal

Read your journal in `.jules/<name>.md` first. Append only *critical, codebase-specific* learnings (a real gotcha, a rejected change + why), never routine logs. Ensure the directory exists before writing.
Format:
```
## YYYY-MM-DD — [Title]
**Learning:** …
**Action:** …
```

## PR Format

Title: "<emoji> <Name>: <one-line change>"
Body:
  💡 What  — the change
  🎯 Why   — the problem it solves
  ⚠️ Risk  — blast radius + how mitigated
  🔬 Verified — exact commands run (py_compile / pytest / ruff / build-deb)
  📎 Scope — files touched; confirm no unrelated changes
