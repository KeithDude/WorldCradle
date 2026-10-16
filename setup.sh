#!/usr/bin/env bash
# GameDash setup for your user account: the Python environment, the settings folder, the
# dashboard's certificate, the background services, and the final "here's how to open it" screen.
#
#   gamedash setup              after installing the GameDash package
#   ./install.sh                from a downloaded copy (installs the system packages, then runs this)
#
# Options:  --fail2ban / --no-fail2ban   set up (or skip) blocking of password guessers; the
#                                        default is to set it up when fail2ban is installed
#           --force                      carry on even if the computer checks fail
#
# Safe to run again at any time: it never overwrites existing settings, passwords, certificate
# or server list. Data: $GAMEDASH_HOME (default ~/.config/gamedash). Backups: $GAMEDASH_BACKUPS
# (default ~/.local/share/gamedash/backups).
set -euo pipefail

GAMEDASH_CODE="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd)"
. "$GAMEDASH_CODE/bin/gamedash-env.sh"
CODE="$GAMEDASH_CODE"; VENV="$GAMEDASH_VENV"; DATA="$GAMEDASH_HOME"; PORT="$GAMEDASH_PORT"
BACKUPS="${GAMEDASH_BACKUPS:-$HOME/.local/share/gamedash/backups}"
UNITS="$HOME/.config/systemd/user"
PACKAGED=0; [ -w "$CODE" ] || PACKAGED=1      # the package's program folder belongs to the system
FAIL2BAN=auto; FORCE=()
for arg in "$@"; do
    case "$arg" in
        --fail2ban) FAIL2BAN=yes ;;
        --no-fail2ban) FAIL2BAN=no ;;
        --force) FORCE=(--force) ;;
        -h|--help) sed -n '2,15p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) echo "Unknown option: $arg  (try --help)"; exit 2 ;;
    esac
done
FROM_INSTALLER="${GAMEDASH_FROM_INSTALLER:-0}"
say()  { printf '\n\033[1;36m== %s\033[0m\n' "$*"; }
note() { printf '   %s\n' "$*"; }

# --- 0. Can this computer run GameDash? (install.sh has already checked) ----------
if [ "$FROM_INSTALLER" != 1 ]; then
    "$CODE/bin/gamedash-preflight" "${FORCE[@]}" || exit 1
fi

# --- 1. Python environment ---------------------------------------------------------
say "Python libraries"
# creates the environment, or rebuilds it if it's missing or broken (e.g. after a Python upgrade)
"$CODE/bin/gamedash-ensure-venv" || exit 1

# --- 2. Settings folder ------------------------------------------------------------
say "Settings: $DATA"
mkdir -p "$DATA/certs" "$DATA/logs" "$BACKUPS"
chmod 700 "$DATA" "$DATA/certs" "$DATA/logs"
[ -f "$DATA/servers.json" ] || cp "$CODE/deploy/examples/servers.json.example" "$DATA/servers.json"
if [ ! -f "$DATA/secrets.conf" ]; then
    # Never start with the example's well-known placeholders: pick random passwords (letters and
    # digits only, which every game accepts). The owner can change them in Settings at any time.
    umask 077
    python3 - "$CODE/deploy/examples/secrets.conf.example" "$DATA/secrets.conf" <<'PW'
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
    chmod 600 "$DATA/secrets.conf"
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
subst "$CODE/deploy/systemd/gamedash.service.in"        > "$UNITS/gamedash.service"
subst "$CODE/deploy/systemd/gamedash-backup.service.in" > "$UNITS/gamedash-backup.service"
cp    "$CODE/deploy/systemd/gamedash-backup.timer"        "$UNITS/gamedash-backup.timer"
systemctl --user daemon-reload
systemctl --user enable --quiet gamedash.service gamedash-backup.timer
systemctl --user restart gamedash.service       # picks up a new version on re-runs
systemctl --user start gamedash-backup.timer
note "The dashboard and the daily 05:00 backup are running."

# The `gamedash` command. The package installs it for everyone; a downloaded copy links it here.
if [ "$PACKAGED" = 0 ]; then
    mkdir -p "$HOME/.local/bin"
    ln -sfn "$CODE/bin/gamedash" "$HOME/.local/bin/gamedash"
    case ":$PATH:" in
        *":$HOME/.local/bin:"*) ;;
        *) note "The gamedash command works in new terminal windows (or after logging in again)." ;;
    esac
fi

# --- 5. Keep running after you log out, and start with the computer --------------------
if loginctl show-user "$USER" -p Linger 2>/dev/null | grep -q 'Linger=yes'; then
    :
elif loginctl enable-linger "$USER" 2>/dev/null || sudo loginctl enable-linger "$USER"; then
    note "GameDash keeps running after you log out and starts with the computer."
else
    note "⚠ Couldn't set GameDash to start with the computer. Run: sudo loginctl enable-linger $USER"
fi

# --- 6. The computer's firewall, if it has one switched on ------------------------------
UFW_ACTIVE=0
if command -v ufw >/dev/null 2>&1 && grep -qs '^ENABLED=yes' /etc/ufw/ufw.conf; then
    UFW_ACTIVE=1
    note "This computer's firewall (ufw) is on — letting the dashboard through (port $PORT); this asks for your password."
    sudo ufw allow "$PORT/tcp" >/dev/null || note "⚠ Couldn't change the firewall. Run: sudo ufw allow $PORT/tcp"
fi

# --- 7. Block people who keep guessing the dashboard password (fail2ban) --------------
if [ "$FAIL2BAN" = auto ]; then
    command -v fail2ban-client >/dev/null 2>&1 && FAIL2BAN=yes || FAIL2BAN=no
fi
if [ "$FAIL2BAN" = yes ]; then
    jail="$(sed -e "s#__GAMEDASH_LOGS__#$DATA/logs#" -e "s#__PORT__#$PORT#" "$CODE/deploy/fail2ban/gamedash-jail.conf")"
    if [ "$jail" = "$(cat /etc/fail2ban/jail.d/gamedash.conf 2>/dev/null)" ] \
       && cmp -s "$CODE/deploy/fail2ban/gamedash-filter.conf" /etc/fail2ban/filter.d/gamedash.conf; then
        :   # already set up
    else
        note "Setting up protection against password guessing (fail2ban) — this asks for your password."
        if printf '%s\n' "$jail" | sudo tee /etc/fail2ban/jail.d/gamedash.conf >/dev/null \
           && sudo cp "$CODE/deploy/fail2ban/gamedash-filter.conf" /etc/fail2ban/filter.d/gamedash.conf \
           && sudo systemctl enable --quiet --now fail2ban && sudo systemctl restart fail2ban; then
            note "Done: an address that gets the dashboard password wrong 4 times is blocked for an hour."
        else
            note "⚠ Couldn't set up fail2ban. GameDash still slows down password guessing by itself."
        fi
    fi
fi

# --- 8. How to open it ----------------------------------------------------------
if [ "$UFW_ACTIVE" = 1 ]; then set -- --firewall; else set --; fi
"$VENV/bin/python" "$CODE/app/cli.py" welcome "$@"
