#!/usr/bin/env bash
# RealmCradle — download and install in one step.
#
#   wget -qO- https://raw.githubusercontent.com/KeithDude/RealmCradle/main/get.sh | bash
#   (or: curl -fsSL …/get.sh | bash — a fresh Ubuntu desktop has wget but not curl)
#
# Installs the newest RealmCradle package from GitHub Releases (checked against its published
# checksum) and sets it up for your account. Later updates: realmcradle update.
# With --from-source, or while no release is published yet, it downloads the source into
# ~/realmcradle with git and runs install.sh instead.
# Other options are passed on (e.g.  ... | bash -s -- --minimal).
set -euo pipefail
PROJECT="KeithDude/RealmCradle"
DEST="${REALMCRADLE_DIR:-$HOME/realmcradle}"
FROM_SOURCE=0; ARGS=()
for arg in "$@"; do
    if [ "$arg" = --from-source ]; then FROM_SOURCE=1; else ARGS+=("$arg"); fi
done

if [ "$(id -u)" = 0 ]; then
    echo "Please run this as your normal user, not as root (no 'sudo' in front)."; exit 1
fi
fetch() {  # fetch URL FILE
    if command -v curl >/dev/null 2>&1; then curl -fsSL "$1" -o "$2"; else wget -qO "$2" "$1"; fi
}

if [ "$FROM_SOURCE" = 0 ]; then
    work="$(mktemp -d)"; trap 'rm -rf "$work"' EXIT
    chmod 755 "$work"     # apt reads the package as its own user, "_apt"
    if fetch "https://api.github.com/repos/$PROJECT/releases/latest" "$work/release.json" 2>/dev/null \
       && python3 - "$work/release.json" > "$work/urls" <<'PICK'
import json, re, sys
assets = {a["name"]: a["browser_download_url"] for a in json.load(open(sys.argv[1])).get("assets", [])}
deb = next(n for n in assets if re.fullmatch(r"realmcradle_[A-Za-z0-9.+~-]+_all\.deb", n))
print(deb, assets[deb], assets[deb + ".sha256"])
PICK
    then
        read -r name deb_url sha_url < "$work/urls"
        echo "== Downloading $name"
        fetch "$deb_url" "$work/$name"
        fetch "$sha_url" "$work/$name.sha256"
        (cd "$work" && sha256sum --check --quiet "$name.sha256") || {
            echo "The download doesn't match its published checksum — not installing. Try again later."; exit 1; }
        # install.sh's options, as the package understands them: --minimal skips the extras
        # (apt's "recommended" packages); the rest go to setup
        APT=(); SETUP=()
        for arg in "${ARGS[@]}"; do
            case "$arg" in
                --minimal) APT+=(--no-install-recommends); SETUP+=(--no-fail2ban) ;;
                --ask|--yes|-y) ;;
                *) SETUP+=("$arg") ;;
            esac
        done
        echo "== Installing it (asks for your computer's admin password)"
        sudo apt-get update -qq
        sudo DEBIAN_FRONTEND=noninteractive apt-get install -y "${APT[@]}" "$work/$name"
        rm -rf "$work"; trap - EXIT
        # when piped from curl, setup's questions need the keyboard, not the pipe
        exec realmcradle setup "${SETUP[@]}" </dev/tty
    fi
    echo "== No RealmCradle package is published yet — installing from the source instead."
fi

if ! command -v git >/dev/null 2>&1; then
    echo "== Installing git (asks for your computer's admin password)"
    sudo apt-get update && sudo apt-get install -y git
fi
if [ -d "$DEST/.git" ]; then
    echo "== Updating RealmCradle in $DEST"
    git -C "$DEST" pull --ff-only
else
    echo "== Downloading RealmCradle into $DEST"
    git clone --depth 1 "https://github.com/$PROJECT.git" "$DEST"
fi
exec bash "$DEST/install.sh" "${ARGS[@]}" </dev/tty
