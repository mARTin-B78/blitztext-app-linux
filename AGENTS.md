# Shared Rules for Jules Agents

## Environment / verify — mirror CI (.github/workflows/ci.yml)

```bash
sudo apt-get update && sudo apt-get install -y \
  python3-gi gir1.2-gtk-3.0 gir1.2-appindicator3-0.1 \
  libgirepository1.0-dev libcairo2-dev python3-dev \
  libgirepository-2.0-dev pkg-config build-essential
cd linux
pip install -r requirements.txt --break-system-packages
pip install pytest ruff PyGObject numpy tomli_w --break-system-packages
python -m py_compile blitztext/*.py     # syntax gate
PYTHONPATH=. pytest tests               # test gate
ruff check blitztext tests              # quality gate
```

## Scope discipline
- **One concern, one small PR.** No drive-by refactors (the repo's CONTRIBUTING says so explicitly).
- **If there's no clear, high-confidence win this run, STOP — don't open a PR.**
- Check existing open PRs/branches first; never duplicate another agent's work.
- Never touch `requirements.txt`, `pyrightconfig.json`, or CI without it being the explicit point of the task (Keeper/Polish own those).
- Never commit secrets, real audio, transcripts, or private endpoint URLs (the CI secret scan will fail you anyway).
- Bump `linux/blitztext/__init__.py` + add a `CHANGELOG.md` entry for any user-visible change. SemVer: fix → patch, feature → minor.

## Journal
Read `.jules/<name>.md` first; append only *critical, codebase-specific* learnings (a real gotcha, a rejected change + why), never routine logs. Format:
```markdown
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

## Defense in depth + least privilege
- Validate every external input (config, the Wyoming server, remote STT/LLM responses).
- Never trust a subprocess argument that came from config.
- Keep the `.deb` maintainer scripts minimal as they run as root.

## Reliability = graceful degradation
- A missing recorder, an unreachable endpoint, a dead Wyoming server must degrade cleanly.
- Never hang or crash the GTK loop.
