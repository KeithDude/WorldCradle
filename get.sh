#!/usr/bin/env bash
# GameDash — get and install in one step.
#
#   curl -fsSL https://raw.githubusercontent.com/KeithDude/GameDash/main/get.sh | bash
#
# Downloads GameDash into ~/gamedash (or updates it if it is already there) and runs the
# installer. Extra words are passed to install.sh, e.g.  ... | bash -s -- --minimal
set -euo pipefail
REPO_URL="${GAMEDASH_REPO:-https://github.com/KeithDude/GameDash.git}"
DEST="${GAMEDASH_DIR:-$HOME/gamedash}"

if [ "$(id -u)" = 0 ]; then
    echo "Please run this as your normal user, not as root (no 'sudo' in front)."; exit 1
fi
if ! command -v git >/dev/null 2>&1; then
    echo "== Installing git (asks for your computer's admin password)"
    sudo apt-get update && sudo apt-get install -y git
fi
if [ -d "$DEST/.git" ]; then
    echo "== Updating GameDash in $DEST"
    git -C "$DEST" pull --ff-only
else
    echo "== Downloading GameDash into $DEST"
    git clone --depth 1 "$REPO_URL" "$DEST"
fi
# when piped from curl, the installer's questions need the keyboard, not the pipe
exec bash "$DEST/install.sh" "$@" </dev/tty
