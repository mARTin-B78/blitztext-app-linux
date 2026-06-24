#!/usr/bin/env bash
# Install Blitztext for Linux from GitHub.
#
# Usage (any Ubuntu/Debian machine):
#   curl -fsSL https://raw.githubusercontent.com/mARTin-B78/blitztext-app-linux/main/install-linux.sh | bash
#
# Or clone first and run locally:
#   git clone https://github.com/mARTin-B78/blitztext-app-linux.git
#   bash blitztext-app-linux/install-linux.sh
#
# What it does:
#   1. Installs build tools (git, fakeroot, dpkg-dev) if missing
#   2. Clones the repo to a temp directory
#   3. Builds a .deb package
#   4. Installs it with apt (pulls in all runtime dependencies)
#   5. Cleans up the temp directory
#
# After install:
#   - "Blitztext" appears in your app grid
#   - Or run: blitztext tray
#   - Remove:  sudo apt remove blitztext
set -euo pipefail

REPO="https://github.com/mARTin-B78/blitztext-app-linux.git"
BRANCH="${BRANCH:-main}"

# --- helpers ----------------------------------------------------------------
info()  { echo -e "\033[1;34m==>\033[0m \033[1m$*\033[0m"; }
ok()    { echo -e "\033[1;32m==>\033[0m \033[1m$*\033[0m"; }
fail()  { echo -e "\033[1;31m==>\033[0m \033[1m$*\033[0m" >&2; exit 1; }

command_exists() { command -v "$1" &>/dev/null; }

# --- preflight --------------------------------------------------------------
info "Blitztext for Linux — installer"

# Detect package manager
if command_exists apt; then
    PKG=apt
elif command_exists apt-get; then
    PKG=apt-get
else
    fail "This installer requires apt (Ubuntu/Debian). For other distros, install from source: see the README."
fi

# Ensure we can sudo
if ! sudo -n true 2>/dev/null; then
    info "This installer needs sudo to install packages."
    sudo true || fail "sudo failed."
fi

# --- install build dependencies ---------------------------------------------
BUILD_DEPS=()
command_exists git      || BUILD_DEPS+=(git)
command_exists fakeroot || BUILD_DEPS+=(fakeroot)
command_exists dpkg-deb || BUILD_DEPS+=(dpkg-dev)

if ((${#BUILD_DEPS[@]})); then
    info "Installing build tools: ${BUILD_DEPS[*]}"
    sudo $PKG install -y "${BUILD_DEPS[@]}"
fi

# --- clone ------------------------------------------------------------------
TMPDIR="$(mktemp -d)"
trap 'rm -rf "$TMPDIR"' EXIT

info "Cloning $REPO ($BRANCH)…"
git clone --depth 1 --branch "$BRANCH" "$REPO" "$TMPDIR/blitztext-app-linux"

# --- build .deb -------------------------------------------------------------
info "Building .deb package…"
LINUX_DIR="$TMPDIR/blitztext-app-linux/linux"
OUT_DIR="$TMPDIR/out"
mkdir -p "$OUT_DIR"
OUT_DIR="$OUT_DIR" bash "$LINUX_DIR/packaging/build-deb.sh"

DEB="$(ls "$OUT_DIR"/*.deb 2>/dev/null | head -1)"
if [ -z "$DEB" ] || [ ! -f "$DEB" ]; then
    fail "Build failed — no .deb produced."
fi

# --- install ----------------------------------------------------------------
info "Installing $(basename "$DEB")…"
sudo $PKG install -y "$DEB"

# --- done -------------------------------------------------------------------
VER="$(dpkg -s blitztext 2>/dev/null | grep '^Version:' | cut -d' ' -f2)"
ok "Blitztext ${VER:-} installed!"
echo ""
echo "  Launch from your app grid, or run:"
echo "    blitztext tray     # system tray (recommended)"
echo "    blitztext gui      # control-panel window"
echo "    blitztext run      # headless, hotkeys only"
echo ""
echo "  For rewrite workflows, set your API key first:"
echo "    export MY_LLM_API_KEY=sk-..."
echo ""
echo "  Remove:"
echo "    sudo apt remove blitztext"
echo ""
