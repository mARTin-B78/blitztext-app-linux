#!/usr/bin/env bash
# Install Blitztext for Linux (no root needed).
#
# Creates a self-contained venv at ~/.local/lib/blitztext (outside any CIFS
# share, using --copies so no symlinks are needed), copies the package into it,
# and writes a launcher to ~/.local/bin/blitztext. The source folder can be
# deleted after this script finishes.
set -euo pipefail

cd "$(dirname "$0")"
APPDIR="$HOME/.local/lib/blitztext"
VENV="$APPDIR/venv"
BIN="$HOME/.local/bin/blitztext"

echo "==> Checking host tools"
need_pkg=()
# python3-gi (PyGObject) must come from apt — it can't be pip-installed.
python3 -c "import gi" 2>/dev/null || need_pkg+=("python3-gi python3-gi-cairo gir1.2-gtk-3.0 gir1.2-appindicator3-0.1")
command -v xdotool    >/dev/null || need_pkg+=("xdotool")
command -v notify-send >/dev/null || need_pkg+=("libnotify-bin")
if ! command -v pw-record >/dev/null && ! command -v arecord >/dev/null && ! command -v parecord >/dev/null; then
    need_pkg+=("pipewire-bin")
fi
if (( ${#need_pkg[@]} )); then
    echo "   Missing system packages — installing now (requires sudo):"
    echo "   sudo apt install ${need_pkg[*]}"
    sudo apt-get install -y "${need_pkg[@]}"
fi

echo "==> Creating venv at $VENV"
mkdir -p "$APPDIR"
# --copies avoids lib64->lib symlinks that fail on CIFS/SMB shares.
# --system-site-packages lets the venv see apt-installed python3-gi for the tray.
python3 -m venv --copies --system-site-packages "$VENV"
"$VENV/bin/pip" install --upgrade pip -q
"$VENV/bin/pip" install -q -r requirements.txt

echo "==> Installing blitztext package"
# Copy the package into site-packages so this source folder can be deleted.
cp -r blitztext "$VENV/lib/python"*/site-packages/

echo "==> Writing default config (if absent)"
"$VENV/bin/python" -m blitztext config-path

echo "==> Installing launcher → $BIN"
mkdir -p "$(dirname "$BIN")"
cat > "$BIN" <<EOF
#!/bin/sh
exec "$VENV/bin/python" -m blitztext "\$@"
EOF
chmod +x "$BIN"

# Copy icons to hicolor so the app shows up properly in the tray / launcher.
ICON_DIR="$HOME/.local/share/icons/hicolor"
PKG_DIR="$(cd "$(dirname "$0")" && pwd)"
for s in 32 48 64 128 256; do
    SRC="$PKG_DIR/packaging/blitztext_${s}.png"
    if [ -f "$SRC" ]; then
        DEST="$ICON_DIR/${s}x${s}/apps/blitztext.png"
        mkdir -p "$(dirname "$DEST")"
        cp "$SRC" "$DEST"
    fi
done
gtk-update-icon-cache -qf "$ICON_DIR" 2>/dev/null || true

cat <<EOF

Done! Blitztext is installed at $APPDIR

Start it:
  blitztext tray    # system tray
  blitztext gui     # control-panel window

(Make sure ~/.local/bin is in your PATH — it is by default on Ubuntu.)

You can now delete the source folder if you cloned it just for installation.
EOF
