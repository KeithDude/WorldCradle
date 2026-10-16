#!/usr/bin/env bash
# GameDash — one-step installer.
#
#   bash install.sh            install everything — no questions (it only asks for your password)
#   bash install.sh --ask      ask before each optional extra (Java, Wine, fail2ban)
#   bash install.sh --minimal  skip the optional extras (add them later by running it again)
#   bash install.sh --check    show what would be done, change nothing
#   bash install.sh --force    install even if the computer checks fail
#
# What it does, in order:
#   1. installs the system packages GameDash and the game servers need
#      (this is the only part that asks for your computer's admin password);
#   2. lets GameDash keep running after you log out and start with the computer;
#   3. sets GameDash itself up (setup.sh) and starts it;
#   4. prints the address to open in your browser and a one-time setup code.
#
# It is safe to run again at any time — nothing already set up is overwritten.
# (--yes is accepted for older instructions; not asking is already the default.)
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
YES=1; CHECK=0; MINIMAL=0; FORCE=0
for arg in "$@"; do
    case "$arg" in
        --yes|-y) YES=1 ;;
        --ask)    YES=0 ;;
        --minimal) MINIMAL=1 ;;
        --check)  CHECK=1 ;;
        --force)  FORCE=1 ;;
        -h|--help) sed -n '2,17p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) echo "Unknown option: $arg  (try --help)"; exit 2 ;;
    esac
done

say()  { printf '\n\033[1;36m== %s\033[0m\n' "$*"; }
note() { printf '   %s\n' "$*"; }
run()  { if [ "$CHECK" = 1 ]; then printf '   would run: %s\n' "$*"; else "$@"; fi; }
ask()  {  # ask "Question?"  → 0 for yes. Default: yes without asking; --ask asks; --minimal says no.
    [ "$MINIMAL" = 1 ] && return 1
    if [ "$YES" = 1 ] || [ "$CHECK" = 1 ]; then return 0; fi
    local reply
    read -r -p "   $1 [Y/n] " reply </dev/tty || reply=""
    case "$reply" in [nN]*) return 1 ;; *) return 0 ;; esac
}

if [ "$(id -u)" = 0 ]; then
    echo "Please run this as your normal user, not as root (no 'sudo' in front)."
    echo "It will ask for your password itself when it needs to install system packages."
    exit 1
fi

# --- 0. Can this computer run GameDash? -----------------------------------------
# Checked before anything is installed. ✗ stops the install (--force to go ahead anyway);
# ⚠ is a warning and the install continues.
PRE_FAIL=0
pre_ok()   { printf '   \033[32m✓\033[0m %s\n' "$*"; }
pre_warn() { printf '   \033[33m⚠\033[0m %s\n' "$*"; }
pre_bad()  { printf '   \033[31m✗\033[0m %s\n' "$*"; PRE_FAIL=1; }
preflight() {
    say "Checking this computer"
    # operating system — the installer uses apt (Ubuntu / Debian)
    local id="" ver="" name=""
    [ -r /etc/os-release ] && . /etc/os-release && id="${ID:-}" ver="${VERSION_ID:-}" name="${PRETTY_NAME:-}"
    if ! command -v apt-get >/dev/null 2>&1; then
        pre_bad "This installer needs Ubuntu or Debian (it uses 'apt'). On another Linux, install the packages listed in deploy/SETUP.md, then run ./setup.sh"
    elif { [ "$id" = ubuntu ] && [ "${ver%%.*}" -ge 22 ] 2>/dev/null; } || { [ "$id" = debian ] && [ "${ver%%.*}" -ge 12 ] 2>/dev/null; }; then
        pre_ok "Operating system: ${name:-$id $ver}"
        if { [ "$id" = ubuntu ] && [ "${ver%%.*}" -lt 24 ]; } || { [ "$id" = debian ] && [ "${ver%%.*}" -lt 13 ]; }; then
            pre_warn "This version offers an older Wine (6.0). Windows-only game servers were tested with Wine 10; some may not work with 6.0 (V Rising does). Linux game servers are unaffected. For the Windows-only ones, Ubuntu 24.04 or newer is the safer choice."
        fi
    else
        pre_warn "Operating system: ${name:-unknown}. GameDash is made for Ubuntu 22.04+ or Debian 12+; it may still work."
    fi
    # processor — game servers are built for 64-bit Intel/AMD processors
    local arch; arch="$(uname -m)"
    if [ "$arch" = x86_64 ]; then
        pre_ok "Processor: 64-bit Intel/AMD ($(nproc) cores)"
    else
        pre_bad "Processor: $arch. Game servers are made for 64-bit Intel/AMD processors (x86_64), so they won't run on this computer (e.g. a Raspberry Pi)."
    fi
    if [ "$arch" = x86_64 ] && ! grep -qw avx /proc/cpuinfo 2>/dev/null; then
        pre_warn "This processor doesn't offer AVX instructions, which some newer game servers need. If this is a virtual machine, set its CPU type to \"host\" in the hypervisor."
    fi
    # memory
    local mem_gb; mem_gb=$(awk '/MemTotal/ {printf "%d", $2/1048576 + 0.5}' /proc/meminfo)
    if [ "$mem_gb" -ge 8 ]; then pre_ok "Memory: ${mem_gb} GB"
    elif [ "$mem_gb" -ge 4 ]; then pre_warn "Memory: ${mem_gb} GB. Enough for GameDash and a small game server; most game servers want 4-16 GB each."
    else pre_bad "Memory: ${mem_gb} GB. Game servers need at least 4 GB; most want much more."; fi
    # disk space where the games will be installed (the home folder)
    local free_gb; free_gb=$(df -Pk "$HOME" | awk 'NR==2 {printf "%d", $4/1048576}')
    if [ "$free_gb" -ge 50 ]; then pre_ok "Free disk space: ${free_gb} GB"
    elif [ "$free_gb" -ge 15 ]; then pre_warn "Free disk space: ${free_gb} GB. Enough to start; many game servers take 5-30 GB each."
    else pre_bad "Free disk space: ${free_gb} GB. Please free up space first — GameDash and one game server need at least 15 GB."; fi
    # background services for this user (GameDash runs as one)
    if systemctl --user show-environment >/dev/null 2>&1; then
        pre_ok "Background services: available"
    else
        pre_bad "Background services (systemd) aren't available for your account here — GameDash needs them. On WSL, enable systemd first; otherwise log in normally (not through 'su') and try again."
    fi
    # the dashboard's port must be free (unless GameDash itself already uses it)
    if command -v ss >/dev/null 2>&1 && ss -tlnH 2>/dev/null | awk '{print $4}' | grep -qE '[:.]8443$' \
       && ! systemctl --user is-active --quiet gamedash 2>/dev/null; then
        pre_bad "Port 8443, which the dashboard uses, is already taken by another program on this computer."
    else
        pre_ok "Dashboard port 8443: free"
    fi
    # internet — needed to download packages and game servers
    if python3 - <<'NET' 2>/dev/null
import sys, urllib.request
for url in ("https://github.com/", "https://steamcdn-a.akamaihd.net/", "https://archive.ubuntu.com/"):
    try:
        urllib.request.urlopen(url, timeout=10); sys.exit(0)
    except Exception as e:   # an HTTP error page still proves the internet works
        if getattr(e, "code", None):
            sys.exit(0)
sys.exit(1)
NET
    then
        pre_ok "Internet connection: working"
    else
        pre_warn "Couldn't reach the internet. Packages and game servers are downloaded during setup — check the connection."
    fi
    if [ "$PRE_FAIL" = 1 ]; then
        echo
        if [ "$FORCE" = 1 ] || [ "$CHECK" = 1 ]; then
            if [ "$CHECK" = 1 ]; then note "(--check: carrying on to show the rest; nothing is changed.)"; else note "Continuing anyway because of --force."; fi
        else
            note "GameDash can't be installed on this computer as it is — see the ✗ lines above."
            note "(To try anyway: bash install.sh --force)"
            exit 1
        fi
    fi
}
preflight
case "$REPO" in
    "$HOME/Downloads"/*|/tmp/*)
        note ""
        note "⚠ GameDash will run from this folder: $REPO"
        note "  Don't delete or move it later. (A tidier place is your home folder, e.g. ~/gamedash —"
        note "  move the folder there now and run install.sh again from the new place, if you like.)"
        ;;
esac

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
    if [ "$CHECK" = 1 ]; then
        run sudo apt-get update
        run sudo apt-get install -y "${MISSING[@]}"
    else
        # apt prints thousands of lines; keep them in a log and show progress instead
        APTLOG="$(mktemp /tmp/gamedash-install-XXXXXX.log)"
        sudo -v || { note "The admin password is needed to install the packages above."; exit 1; }
        note "Downloading and installing — this can take several minutes…"
        if ! { sudo apt-get update && sudo DEBIAN_FRONTEND=noninteractive apt-get install -y "${MISSING[@]}"; } >"$APTLOG" 2>&1; then
            note "Installing the packages failed. The last lines of the log ($APTLOG):"
            tail -n 15 "$APTLOG" | sed 's/^/     /'
            exit 1
        fi
        note "Done. (Full details: $APTLOG)"
    fi
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
export GAMEDASH_FROM_INSTALLER=1
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

     On a phone: scan this code with the camera (phone on the same Wi-Fi).
EOF
"$REPO/venv/bin/python" "$REPO/app/cli.py" qr 2>/dev/null | tail -n +2 | sed 's/^/     /' || true
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
JOINPW="$("$REPO/venv/bin/python" "$REPO/app/cli.py" passwords --join 2>/dev/null || true)"
cat <<EOF

  3. Follow the "Getting started" checklist on the dashboard: install a game,
     add a server, and check that friends can connect.
EOF
if [ -n "$JOINPW" ]; then
    cat <<EOF

  Your friends will need this password to join your game servers:

         $JOINPW

     (Change it any time in the dashboard: Settings → Game passwords.
      To see it again later, type:  gamedash passwords)
EOF
fi
if [ "$UFW_ACTIVE" = 1 ]; then
    cat <<EOF

  Note: this computer's firewall (ufw) is on. Each game server's ports also have
  to be allowed through it. After adding a server, open "Can friends connect?" on
  its card for the list, then run for each port, e.g.:  sudo ufw allow 7777/udp
EOF
fi
echo
