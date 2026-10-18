#!/usr/bin/env bash
# WorldCradle — install from a downloaded copy (the WorldCradle package doesn't need this: after
# installing it, run "worldcradle setup").
#
#   bash install.sh            install everything — no questions (it only asks for your password)
#   bash install.sh --ask      ask before each optional extra (Java, Wine, fail2ban)
#   bash install.sh --minimal  skip the optional extras (add them later by running it again)
#   bash install.sh --check    show what would be done, change nothing
#   bash install.sh --force    install even if the computer checks fail
#
# What it does, in order:
#   1. checks this computer can run WorldCradle;
#   2. installs the system packages WorldCradle and the game servers need (deploy/packages.conf) —
#      the only part that needs your computer's admin password;
#   3. sets WorldCradle up for your account and starts it (setup.sh), then shows the address to open
#      in your browser and a one-time setup code.
#
# It is safe to run again at any time — nothing already set up is overwritten.
# (--yes is accepted for older instructions; not asking is already the default.)
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
YES=1; CHECK=0; MINIMAL=0; FORCE=()
for arg in "$@"; do
    case "$arg" in
        --yes|-y) YES=1 ;;
        --ask)    YES=0 ;;
        --minimal) MINIMAL=1 ;;
        --check)  CHECK=1 ;;
        --force)  FORCE=(--force) ;;
        -h|--help) sed -n '2,18p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) echo "Unknown option: $arg  (try --help)"; exit 2 ;;
    esac
done

say()  { printf '\n\033[1;36m== %s\033[0m\n' "$*"; }
note() { printf '   %s\n' "$*"; }
ask()  {  # ask "Question?"  → 0 for yes. Default: yes without asking; --ask asks; --minimal says no.
    [ "$MINIMAL" = 1 ] && return 1
    if [ "$YES" = 1 ] || [ "$CHECK" = 1 ]; then return 0; fi
    local reply
    read -r -p "   $1 [Y/n] " reply </dev/tty || reply=""
    case "$reply" in [nN]*) return 1 ;; *) return 0 ;; esac
}
# The packages in one group of deploy/packages.conf; for "a | b" alternatives, the first one
# this system offers.
packages() {
    local line alt pkg
    line="$(sed -n "s/^$1:[[:space:]]*//p" "$REPO/deploy/packages.conf")"
    if [[ "$line" == *"|"* ]]; then
        IFS='|' read -ra alts <<< "$line"
        for alt in "${alts[@]}"; do
            pkg="$(echo "$alt" | xargs)"
            if apt-cache show "$pkg" >/dev/null 2>&1; then echo "$pkg"; return; fi
        done
    else
        echo "$line"
    fi
}

# --- 1. Can this computer run WorldCradle? -------------------------------------------
if [ "$CHECK" = 1 ]; then
    "$REPO/bin/worldcradle-preflight" --check
else
    "$REPO/bin/worldcradle-preflight" "${FORCE[@]}" || exit 1
fi
case "$REPO" in
    "$HOME/Downloads"/*|/tmp/*)
        note ""
        note "⚠ WorldCradle will run from this folder: $REPO"
        note "  Don't delete or move it later. (A tidier place is your home folder, e.g. ~/worldcradle —"
        note "  move the folder there now and run install.sh again from the new place, if you like.)"
        ;;
esac

# --- 2. System packages -------------------------------------------------------
say "System packages"
read -ra WANT <<< "$(packages required) $(packages games)"
if [ "$YES" = 0 ]; then note "Some games need an extra program. Say yes only for the games you might host."
elif [ "$MINIMAL" = 0 ]; then note "Also installing the extras some games need: Java (Minecraft), Wine (Windows-only servers) and fail2ban (blocks password guessing). Skip them with --minimal."; fi
if ask "Minecraft (needs Java, about 200 MB)?"; then
    WANT+=("$(packages java)")
fi
if ask "Minecraft Bedrock, Terraria, Factorio and the other Linux games need nothing extra. Windows-only servers (Abiotic Factor, Enshrouded, V Rising, Conan Exiles, Sons of the Forest, Icarus, ARK: Survival Ascended, Space Engineers) need Wine, about 1 GB — install it?"; then
    read -ra more <<< "$(packages wine)"; WANT+=("${more[@]}")
    if ask "Also Space Engineers (needs two small helper tools, winetricks and cabextract)?"; then
        read -ra more <<< "$(packages wine-extras)"; WANT+=("${more[@]}")
    fi
fi
FAIL2BAN=--no-fail2ban
if ask "Block people who keep guessing the dashboard password (installs fail2ban — recommended)?"; then
    WANT+=("$(packages fail2ban)"); FAIL2BAN=--fail2ban
fi

MISSING=()
for p in "${WANT[@]}"; do
    if [ -n "$p" ] && ! dpkg -s "$p" >/dev/null 2>&1; then MISSING+=("$p"); fi
done
if [ "${#MISSING[@]}" -eq 0 ]; then
    note "Everything needed is already installed."
elif [ "$CHECK" = 1 ]; then
    note "would install: ${MISSING[*]}"
else
    note "To install: ${MISSING[*]}"
    note "This needs your computer's admin password (the one you log in with)."
    # apt prints thousands of lines; keep them in a log and show progress instead
    APTLOG="$(mktemp /tmp/worldcradle-install-XXXXXX.log)"
    sudo -v || { note "The admin password is needed to install the packages above."; exit 1; }
    note "Downloading and installing — this can take several minutes…"
    if ! { sudo apt-get update && sudo DEBIAN_FRONTEND=noninteractive apt-get install -y "${MISSING[@]}"; } >"$APTLOG" 2>&1; then
        note "Installing the packages failed. The last lines of the log ($APTLOG):"
        tail -n 15 "$APTLOG" | sed 's/^/     /'
        exit 1
    fi
    note "Done. (Full details: $APTLOG)"
fi

# --- 3. WorldCradle itself --------------------------------------------------------
if [ "$CHECK" = 1 ]; then
    note "would run: setup.sh $FAIL2BAN   (nothing was changed)"
    exit 0
fi
WORLDCRADLE_FROM_INSTALLER=1 exec "$REPO/setup.sh" "$FAIL2BAN"
