#!/usr/bin/env bash
# Build a self-contained .deb for Blitztext (Ubuntu/Debian, arm64).
#
# Bundles a relocatable venv with the Python deps from requirements.txt under
# /opt/blitztext so installation needs no pip/network. System
# integration (python3-gi, xdotool, libnotify-bin, a recorder) is declared via
# Depends so the Software app / apt pull them in.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
LINUX_DIR="$(dirname "$HERE")"            # .../linux
PKG="blitztext"
ARCH="$(dpkg --print-architecture)"
VER="$(sed -n 's/.*__version__ = "\(.*\)".*/\1/p' "$LINUX_DIR/blitztext/__init__.py")"
PYBIN="${PYBIN:-/usr/bin/python3}"

BUILD="$(mktemp -d)"
ROOT="$BUILD/${PKG}_${VER}_${ARCH}"
OUT_DIR="${OUT_DIR:-$LINUX_DIR/dist}"
trap 'rm -rf "$BUILD"' EXIT

echo "==> Building $PKG $VER ($ARCH) with $($PYBIN --version)"

# 1) Bundled, relocatable venv with all Python deps -------------------------
APPDIR="$ROOT/opt/$PKG"
VENV="$APPDIR/venv"
mkdir -p "$APPDIR"
"$PYBIN" -m venv --copies "$VENV"
"$VENV/bin/pip" install --upgrade pip -q
"$VENV/bin/pip" install -q -r "$LINUX_DIR/requirements.txt" tomli-w

# Drop the app package into the venv so `python -m blitztext` works.
cp -r "$LINUX_DIR/blitztext" "$VENV/lib/python"*/site-packages/

# Let the venv also see the system PyGObject (apt python3-gi) for tray mode,
# while still preferring its own bundled deps.
PYVENV="$VENV/pyvenv.cfg"
sed -i 's/^include-system-site-packages = false/include-system-site-packages = true/' "$PYVENV"
grep -q "^include-system-site-packages = true" "$PYVENV" || echo "include-system-site-packages = true" >> "$PYVENV"

# Trim build cruft to shrink the package.
find "$VENV" -type d -name "__pycache__" -prune -exec rm -rf {} + 2>/dev/null || true
rm -rf "$VENV/lib/python"*/site-packages/pip "$VENV/lib/python"*/site-packages/pip-* \
       "$VENV"/bin/pip* "$VENV/lib/python"*/site-packages/setuptools* 2>/dev/null || true

cp "$LINUX_DIR/README.md" "$LINUX_DIR/CHANGELOG.md" "$APPDIR/"
# MANUAL.md lives at repo root (one level above linux/)
REPO_MANUAL="$(dirname "$LINUX_DIR")/MANUAL.md"
[ -f "$REPO_MANUAL" ] && cp "$REPO_MANUAL" "$APPDIR/MANUAL.md"

# 2) Launcher, desktop entry, icon, docs ------------------------------------
install -Dm755 /dev/stdin "$ROOT/usr/bin/$PKG" <<'EOF'
#!/bin/sh
exec /opt/blitztext/venv/bin/python -m blitztext "$@"
EOF

install -Dm644 "$HERE/$PKG.desktop"  "$ROOT/usr/share/applications/$PKG.desktop"
install -Dm644 "$HERE/copyright"     "$ROOT/usr/share/doc/$PKG/copyright"
# App icon (extracted from the macOS AppIcon) at several hicolor sizes.
for s in 32 48 64 128 256; do
    install -Dm644 "$HERE/${PKG}_${s}.png" "$ROOT/usr/share/icons/hicolor/${s}x${s}/apps/${PKG}.png"
done

# 3) DEBIAN control + maintainer scripts ------------------------------------
SIZE_KB="$(du -sk "$ROOT" | cut -f1)"
mkdir -p "$ROOT/DEBIAN"
cat > "$ROOT/DEBIAN/control" <<EOF
Package: $PKG
Version: $VER
Section: utils
Priority: optional
Architecture: $ARCH
Depends: python3 (>= 3.12), python3-gi, gir1.2-ayatanaappindicator3-0.1, xdotool, libnotify-bin, pipewire-bin | pulseaudio-utils | alsa-utils
Maintainer: Martin Bierschenk <mail@martin-bierschenk.de>
Installed-Size: $SIZE_KB
Description: Blitztext - local voice dictation for Linux
 Focus any text field, press a hotkey, speak, and the transcribed text is
 typed into that field. Optional LLM rewrite turns rough speech into a nicer
 email, a calmer message, or adds emojis.
 .
 Transcription runs locally via faster-whisper; the optional rewrite uses any
 OpenAI-compatible endpoint (OpenAI or a local server). Runs in the system
 tray or as a small control-panel window. Requires an X11 session.
EOF

cat > "$ROOT/DEBIAN/postinst" <<'EOF'
#!/bin/sh
set -e
if [ "$1" = "configure" ]; then
    gtk-update-icon-cache -qf /usr/share/icons/hicolor 2>/dev/null || true
    update-desktop-database -q 2>/dev/null || true
fi
EOF
chmod 755 "$ROOT/DEBIAN/postinst"

cat > "$ROOT/DEBIAN/postrm" <<'EOF'
#!/bin/sh
set -e
# Remove runtime-generated files (e.g. *.pyc) left in the bundled venv.
if [ "$1" = "remove" ] || [ "$1" = "purge" ]; then
    rm -rf /opt/blitztext
fi
EOF
chmod 755 "$ROOT/DEBIAN/postrm"

# 4) Build -------------------------------------------------------------------
mkdir -p "$OUT_DIR"
DEB="$OUT_DIR/${PKG}_${VER}_${ARCH}.deb"
fakeroot dpkg-deb --build --root-owner-group "$ROOT" "$DEB" >/dev/null
chmod 644 "$DEB"
# Also copy to ~ so `sudo apt install ~/blitztext_*.deb` works without a separate cp
DEST="$HOME/$(basename "$DEB")"
install -m644 "$DEB" "$DEST"
echo "==> Built: $DEB ($(du -h "$DEB" | cut -f1))"
echo "==> Copied: $DEST"
