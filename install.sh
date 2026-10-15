#!/usr/bin/env bash
# GameDash — one-step installer.
#
#   bash install.sh            install everything — no questions (it only asks for your password)
#   bash install.sh --ask      ask before each optional extra (Java, Wine, fail2ban)
#   bash install.sh --minimal  skip the optional extras (add them later by running it again)
#   bash install.sh --check    show what would be done, change nothing
#
# What it does, in order:
#   1. installs the system packages GameDash and the game servers need
#      (this is the only part that asks for your computer's admin password);
#   2. lets GameDash keep running after you log out and start with the computer;
#   3. sets GameDash itself up (setup.sh) and starts it;
#   4. prints the address to open in your browser and a one-time setup code.
#
# It is safe to run again at any time — nothing already set up is overwritten.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
YES=1; CHECK=0; MINIMAL=0
for arg in "$@"; do
    case "$arg" in
        --yes|-y) YES=1 ;;
        --ask)    YES=0 ;;
        --minimal) MINIMAL=1 ;;
        --check)  CHECK=1 ;;
        -h|--help) sed -n '2,17p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) echo "Unknown option: $arg  (try --help)"; exit 2 ;;
    esac
done

say()  { printf '\n\033[1;36m== %s\033[0m\n' "$*"; }
note() { printf '   %s\n' "$*"; }
run()  { if [ "$CHECK" = 1 ]; then printf '   would run: %s\n' "$*"; else "$@"; fi; }
ask()  {  # ask "Question?"  → 0 for yes. Default: yes without asking; --ask asks; --minimal says no.
    [ "$MINIMAL" = 1 ] && return 1
    [ "$YES" = 1 ] || [ "$CHECK" = 1 ] && return 0
    local reply
    read -r -p "   $1 [Y/n] " reply </dev/tty || reply=""
    case "$reply" in [nN]*) return 1 ;; *) return 0 ;; esac
}

if [ "$(id -u)" = 0 ]; then
    echo "Please run this as your normal user, not as root (no 'sudo' in front)."
    echo "It will ask for your password itself when it needs to install system packages."
    exit 1
fi
if ! command -v apt-get >/dev/null 2>&1; then
    echo "This installer supports Ubuntu and Debian (it uses 'apt')."
    echo "On another Linux, install the packages listed in deploy/SETUP.md, then run ./setup.sh"
    exit 1
fi

# --- 1. System packages -------------------------------------------------------
say "Step 1 of 4 — system packages"
# always needed: Python for the dashboard, and the libraries game servers load
PKGS=(python3 python3-venv python3-pip openssl curl ca-certificates
      lib32gcc-s1      # Valve's server downloader (steamcmd) is a 32-bit program
      libatomic1 libpulse0    # Valheim's server
      xvfb libxi6             # an invisible display some servers need (Core Keeper, V Rising, Sons of the Forest)
      libgdiplus)             # Eco's server
EXTRAS=()
if [ "$YES" = 0 ]; then note "Some games need an extra program. Say yes only for the games you might host."
elif [ "$MINIMAL" = 0 ]; then note "Also installing the extras some games need: Java (Minecraft), Wine (Windows-only servers) and fail2ban (blocks password guessing). Skip them with --minimal."; fi
if ask "Minecraft (needs Java, about 200 MB)?"; then
    # Recent Minecraft versions need a recent Java; take the newest the system offers.
    JAVA_PKG="default-jre-headless"
    for v in 25 21; do
        if apt-cache show "openjdk-$v-jre-headless" >/dev/null 2>&1; then JAVA_PKG="openjdk-$v-jre-headless"; break; fi
    done
    EXTRAS+=("$JAVA_PKG")
fi
if ask "Minecraft Bedrock, Terraria, Factorio and the other Linux games need nothing extra. Windows-only servers (Abiotic Factor, Enshrouded, V Rising, Conan Exiles, Sons of the Forest, Icarus, ARK: Survival Ascended, Space Engineers) need Wine, about 1 GB — install it?"; then
    EXTRAS+=(wine)
    if ask "Also Space Engineers (needs two small helper tools, winetricks and cabextract)?"; then
        EXTRAS+=(winetricks cabextract)
    fi
fi
WANT_F2B=0
if ask "Block people who keep guessing the dashboard password (installs fail2ban — recommended)?"; then
    EXTRAS+=(fail2ban); WANT_F2B=1
fi

MISSING=()
for p in "${PKGS[@]}" "${EXTRAS[@]}"; do
    dpkg -s "$p" >/dev/null 2>&1 || MISSING+=("$p")
done
if [ "${#MISSING[@]}" -eq 0 ]; then
    note "Everything needed is already installed."
else
    note "To install: ${MISSING[*]}"
    note "This needs your computer's admin password (the one you log in with)."
    run sudo apt-get update
    run sudo apt-get install -y "${MISSING[@]}"
fi

# --- 2. Keep running after logout / start at boot -----------------------------
say "Step 2 of 4 — keep GameDash running"
if loginctl show-user "$USER" -p Linger 2>/dev/null | grep -q 'Linger=yes'; then
    note "Already set to keep running after you log out and to start with the computer."
else
    run sudo loginctl enable-linger "$USER"
fi

# If this computer runs the 'ufw' firewall, the dashboard's port must be let through.
if command -v ufw >/dev/null 2>&1 && sudo -n ufw status 2>/dev/null | grep -q 'Status: active'; then
    note "A firewall (ufw) is active — allowing the dashboard through it (port 8443)."
    run sudo ufw allow 8443/tcp
    UFW_ACTIVE=1
else
    UFW_ACTIVE=0
fi

# --- 3. GameDash itself --------------------------------------------------------
say "Step 3 of 4 — GameDash"
if [ "$WANT_F2B" = 1 ]; then run "$REPO/setup.sh" --fail2ban; else run "$REPO/setup.sh"; fi

# --- 4. Where to go next -------------------------------------------------------
say "Step 4 of 4 — finished"
if [ "$CHECK" = 1 ]; then
    note "(--check: nothing was changed)"
    exit 0
fi
IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
DATA="${GAMEDASH_HOME:-$HOME/.config/gamedash}"
CODE="$(GAMEDASH_HOME="$DATA" "$REPO/venv/bin/python" "$REPO/app/manage.py" setup-code 2>/dev/null || true)"
cat <<EOF

  GameDash is running.

  1. On any computer or phone on your home network, open a web browser and go to:

         https://${IP:-this-computer}:8443/

     The browser will warn that the connection is "not private". That is expected
     the first time: choose "Advanced", then "Proceed" / "Accept the risk".
EOF
if [ -n "$CODE" ]; then
    cat <<EOF

  2. Enter this one-time setup code and choose your password:

         $CODE

     (Lost it? Run this installer again to get a new one.)
EOF
else
    cat <<EOF

  2. Sign in with the admin password you already chose.
EOF
fi
cat <<EOF

  3. Follow the "Getting started" checklist on the dashboard: install a game,
     add a server, and check that friends can connect.
EOF
if [ "$UFW_ACTIVE" = 1 ]; then
    cat <<EOF

  Note: this computer's firewall (ufw) is on. Each game server's ports also have
  to be allowed through it. After adding a server, open "Can friends connect?" on
  its card for the list, then run for each port, e.g.:  sudo ufw allow 7777/udp
EOF
fi
echo
