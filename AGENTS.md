# Jules Agent Guidelines for Blitztext

This file contains shared rules and environment setup for all Jules agents patrolling this codebase.
If you are a Jules agent, you MUST obey these instructions.

## Shared Setup / Environment

Every Jules run must start from a working environment. Mirror the CI setup (`.github/workflows/ci.yml`):

```bash
sudo apt-get update && sudo apt-get install -y \
  python3-gi gir1.2-gtk-3.0 gir1.2-appindicator3-0.1 \
  libgirepository1.0-dev libgirepository-2.0-dev \
  pkg-config build-essential libcairo2-dev python3-dev

cd linux
pip install -r requirements.txt
pip install pytest ruff PyGObject numpy

python -m py_compile blitztext/*.py     # syntax gate
PYTHONPATH=. pytest tests               # test gate
ruff check blitztext tests              # quality gate
```

## Scope Discipline

- **One concern, one small PR.** No drive-by refactors.
- **If there's no clear, high-confidence win this run, STOP — don't open a PR.**
- Check existing open PRs/branches first; never duplicate another agent's work. Keep a human merge gate on every PR.
- Never touch `requirements.txt`, `pyrightconfig.json`, or CI configurations without it being the explicit point of the task.
- Never commit secrets, real audio, transcripts, or private endpoint URLs (use `"<your_api_key_here>"` for safe placeholders).
- Code must degrade gracefully (e.g., handling missing recorders, unreachable endpoints, or dead Wyoming servers cleanly) and never hang or crash the GTK main loop.
- Bump `linux/blitztext/__init__.py` + add a `CHANGELOG.md` entry for any user-visible change. SemVer: fix → patch, feature → minor.
- Preserve the inspiration credit attributing 'cmagnussen/blitztext-app' when modifying project-facing documentation.

## Journal

Read `.jules/<name>.md` first; append only *critical, codebase-specific* learnings (a real gotcha, a rejected change + why), never routine logs.

Format:
```markdown
## YYYY-MM-DD — [Title]
**Learning:** ...
**Action:** ...
```

## PR Format

Title: `<emoji> <Name>: <one-line change>`
Body:
```markdown
💡 What  — the change
🎯 Why   — the problem it solves
⚠️ Risk  — blast radius + how mitigated
🔬 Verified — exact commands run (py_compile / pytest / ruff / build-deb)
📎 Scope — files touched; confirm no unrelated changes
```

## Security & Reliability

- **Shift left + small PRs.** Catch issues in review.
- **Defense in depth + least privilege.** Validate external inputs; never trust subprocess arguments from config; keep `.deb` root scripts minimal.
- **Dependency hygiene.** Pin, audit, and know transitive licenses.
- **Privacy by design.** Temp-only audio, no transcript logging, keys from env only, remote endpoints honestly disclosed.
- **Traceability.** SemVer + CHANGELOG for user-visible changes.
