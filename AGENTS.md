# Shared Rules for Jules Agents

## Environment Setup
Run these commands to set up the environment before making changes:

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
