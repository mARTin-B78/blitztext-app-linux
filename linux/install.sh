#!/usr/bin/env bash
# Set up Blitztext for Linux: create a venv, install deps, check host tools,
# and write the default config. Run from the linux/ directory.
set -euo pipefail

cd "$(dirname "$0")"
VENV=".venv"

echo "==> Checking host tools"
need_pkg=()
command -v xdotool   >/dev/null || need_pkg+=("xdotool")
command -v notify-send >/dev/null || need_pkg+=("libnotify-bin")
if ! command -v pw-record >/dev/null && ! command -v arecord >/dev/null && ! command -v parecord >/dev/null; then
  need_pkg+=("pipewire-bin (or alsa-utils)")
fi
if ((${#need_pkg[@]})); then
  echo "   Missing host tools: ${need_pkg[*]}"
  echo "   On Ubuntu/Debian:  sudo apt install xdotool libnotify-bin pipewire-bin"
  echo "   (continuing — install them before running the daemon)"
fi

# --system-site-packages lets the venv see an apt-installed PyGObject (python3-gi)
# for the optional system-tray mode; harmless if it's not installed.
echo "==> Creating venv at $VENV"
python3 -m venv --system-site-packages "$VENV"
"$VENV/bin/pip" install --upgrade pip -q
"$VENV/bin/pip" install -r requirements.txt

echo "==> Writing default config (if absent)"
"$VENV/bin/python" -m blitztext config-path

cat <<EOF

Done. To start it:

  $VENV/bin/python -m blitztext tray   # system tray (needs: sudo apt install python3-gi)
  $VENV/bin/python -m blitztext gui    # control-panel window
  $VENV/bin/python -m blitztext run    # headless, hotkeys only

Edit your config (hotkeys, Whisper model, rewrite endpoint) at:

  \$($VENV/bin/python -m blitztext config-path)

For the rewrite workflows, export your key first, e.g.:

  export OPENAI_API_KEY=sk-...

To run it in the background on login, see blitztext.service in this folder.
EOF
