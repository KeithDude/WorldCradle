#!/usr/bin/env bash
# WorldCradle setup for your user account: the Python environment, the settings folder, the
# dashboard's certificate, the background services, and the final "here's how to open it" screen.
#
#   worldcradle setup              after installing the WorldCradle package
#   sudo bash install.sh           from a downloaded copy (installs the system packages, then runs this)
#
# It never asks for a password: the parts that need administrator rights (starting with the computer,
# the firewall, fail2ban) are done by the package when it is installed, or by `sudo bash install.sh`
# (bin/worldcradle-system-setup). If one of them is missing, it says which command to run.
#
# Options:  --force                      carry on even if the computer checks fail
#
# Safe to run again at any time: it never overwrites existing settings, passwords, certificate
# or server list. Data: $WORLDCRADLE_HOME (default ~/.config/worldcradle). Backups: $WORLDCRADLE_BACKUPS
# (default ~/.local/share/worldcradle/backups).
set -euo pipefail

WORLDCRADLE_CODE="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd)"
. "$WORLDCRADLE_CODE/bin/worldcradle-env.sh"
CODE="$WORLDCRADLE_CODE"; VENV="$WORLDCRADLE_VENV"; DATA="$WORLDCRADLE_HOME"; PORT="$WORLDCRADLE_PORT"
BACKUPS="${WORLDCRADLE_BACKUPS:-$HOME/.local/share/worldcradle/backups}"
UNITS="$HOME/.config/systemd/user"
PACKAGED=0; [ -w "$CODE" ] || PACKAGED=1      # the package's program folder belongs to the system
FORCE=()
for arg in "$@"; do
    case "$arg" in
        --fail2ban|--no-fail2ban) ;;      # older instructions; fail2ban is set up with the package now
        --force) FORCE=(--force) ;;
        -h|--help) sed -n '2,17p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) echo "Unknown option: $arg  (try --help)"; exit 2 ;;
    esac
done
FROM_INSTALLER="${WORLDCRADLE_FROM_INSTALLER:-0}"
say()  { printf '\n\033[1;36m== %s\033[0m\n' "$*"; }
note() { printf '   %s\n' "$*"; }

# --- 0. Can this computer run WorldCradle? (install.sh has already checked) ----------
if [ "$FROM_INSTALLER" != 1 ]; then
    "$CODE/bin/worldcradle-preflight" "${FORCE[@]}" || exit 1
fi

# --- 1. Python environment ---------------------------------------------------------
say "Python libraries"
# creates the environment, or rebuilds it if it's missing or broken (e.g. after a Python upgrade)
"$CODE/bin/worldcradle-ensure-venv" || exit 1

# --- 2. Settings folder ------------------------------------------------------------
say "Settings: $DATA"
mkdir -p "$DATA/certs" "$DATA/logs" "$BACKUPS"
chmod 700 "$DATA" "$DATA/certs" "$DATA/logs"
[ -f "$DATA/servers.json" ] || cp "$CODE/deploy/examples/servers.json.example" "$DATA/servers.json"
# where the game passwords are kept: secrets.conf here, unless the settings name another file
SECRETS="$(python3 - "$DATA/config.json" "$DATA/secrets.conf" <<'WHERE'
import json, os, sys
try:
    print(os.path.expanduser(json.load(open(sys.argv[1])).get("secrets_conf") or sys.argv[2]))
except (OSError, ValueError):
    print(sys.argv[2])
WHERE
)"
if [ ! -f "$SECRETS" ]; then
    # Never start with the example's well-known placeholders: pick random passwords (letters and
    # digits only, which every game accepts). The owner can change them in Settings at any time.
    umask 077
    python3 - "$CODE/deploy/examples/secrets.conf.example" "$SECRETS" <<'PW'
import re, secrets, sys
src, dst = sys.argv[1:3]
abc = "abcdefghjkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"     # no look-alike characters
pick = lambda n: "".join(secrets.choice(abc) for _ in range(n))
t = open(src, encoding="utf-8").read()
t = re.sub(r'(?m)^GAME_SERVER_PASSWORD=.*$', f'GAME_SERVER_PASSWORD="{pick(10)}"', t)
t = re.sub(r'(?m)^GAME_ADMIN_PASSWORD=.*$', f'GAME_ADMIN_PASSWORD="{pick(20)}"', t)
open(dst, "w", encoding="utf-8").write(t)
PW
    umask 022
    chmod 600 "$SECRETS"
    note "Picked random game passwords — see or change them in the dashboard (Settings → Game passwords)."
fi

# --- 3. The dashboard's certificate (self-signed; a trusted one can be added in Settings) ---
if [ ! -f "$DATA/certs/cert.pem" ]; then
    HOSTN="$(hostname -f 2>/dev/null || hostname)"
    openssl req -x509 -newkey rsa:2048 -nodes -days 3650 \
        -keyout "$DATA/certs/key.pem" -out "$DATA/certs/cert.pem" \
        -subj "/CN=$HOSTN" \
        -addext "subjectAltName=DNS:$HOSTN,DNS:localhost,IP:127.0.0.1" 2>/dev/null
    chmod 600 "$DATA/certs/"*.pem
    note "Made the dashboard's certificate (browsers warn about it once — expected)."
fi

# --- 4. Background services: the dashboard and the daily backup ----------------------
say "Background services"
mkdir -p "$UNITS"
subst() { sed -e "s#__CODE__#$CODE#g" -e "s#__VENV__#$VENV#g" -e "s#__DATA__#$DATA#g" -e "s#__PORT__#$PORT#g" "$1"; }
subst "$CODE/deploy/systemd/worldcradle.service.in"        > "$UNITS/worldcradle.service"
subst "$CODE/deploy/systemd/worldcradle-backup.service.in" > "$UNITS/worldcradle-backup.service"
cp    "$CODE/deploy/systemd/worldcradle-backup.timer"        "$UNITS/worldcradle-backup.timer"
systemctl --user daemon-reload
systemctl --user enable --quiet worldcradle.service worldcradle-backup.timer
systemctl --user restart worldcradle.service       # picks up a new version on re-runs
systemctl --user start worldcradle-backup.timer
note "The dashboard and the daily 05:00 backup are running."

# The `worldcradle` command. The package installs it for everyone; a downloaded copy links it here.
if [ "$PACKAGED" = 0 ]; then
    mkdir -p "$HOME/.local/bin"
    ln -sfn "$CODE/bin/worldcradle" "$HOME/.local/bin/worldcradle"
    case ":$PATH:" in
        *":$HOME/.local/bin:"*) ;;
        *) note "The worldcradle command works in new terminal windows (or after logging in again)." ;;
    esac
fi

# --- 5. Keep running after you log out, and start with the computer --------------------
# (normally done by the package or install.sh, as root; --no-ask-password: never prompt here)
if [ "$PACKAGED" = 1 ]; then AS_ROOT="sudo dpkg-reconfigure worldcradle"; else AS_ROOT="sudo bash $CODE/install.sh"; fi
if loginctl show-user "$USER" -p Linger 2>/dev/null | grep -q 'Linger=yes'; then
    :
elif loginctl --no-ask-password enable-linger "$USER" 2>/dev/null; then
    note "WorldCradle keeps running after you log out and starts with the computer."
else
    note "⚠ WorldCradle won't start by itself when the computer starts. To fix it, run:  sudo loginctl enable-linger $USER"
fi

# --- 6. The computer's firewall, if it has one switched on ------------------------------
UFW_ACTIVE=0
if command -v ufw >/dev/null 2>&1 && grep -qs '^ENABLED=yes' /etc/ufw/ufw.conf; then
    UFW_ACTIVE=1
    if [ "$PORT" != 8443 ]; then     # the package let the usual port (8443) through
        note "This computer's firewall (ufw) is on. To let the dashboard through, run:  sudo ufw allow $PORT/tcp"
    fi
fi

# --- 7. Block people who keep guessing the dashboard password (fail2ban) --------------
if command -v fail2ban-client >/dev/null 2>&1 && [ ! -e /etc/fail2ban/jail.d/worldcradle.conf ]; then
    note "fail2ban is installed but not yet watching WorldCradle's sign-ins. To set it up, run:  $AS_ROOT"
fi

# --- 8. How to open it ----------------------------------------------------------
if [ "$UFW_ACTIVE" = 1 ]; then set -- --firewall; else set --; fi
"$VENV/bin/python" "$CODE/app/cli.py" welcome "$@"
