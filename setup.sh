#!/usr/bin/env bash
# GameDash installer — sets up the venv, data root, self-signed TLS cert,
# systemd user units + daily-backup timer, and linger. Idempotent and
# non-destructive: it never overwrites an existing config/secrets/cert/servers.
#
# Usage:
#   ./setup.sh                 full install (venv, data, cert, units, linger)
#   ./setup.sh --fail2ban      also install the fail2ban jail (needs sudo)
#
# Data root: $GAMEDASH_HOME (default ~/.config/gamedash). Backups:
# $GAMEDASH_BACKUPS (default ~/.local/share/gamedash/backups).
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP="$REPO/app"
VENV="$REPO/venv"
DATA="${GAMEDASH_HOME:-$HOME/.config/gamedash}"
BACKUPS="${GAMEDASH_BACKUPS:-$HOME/.local/share/gamedash/backups}"
UNITS="$HOME/.config/systemd/user"
say() { printf '\n\033[1;36m== %s\033[0m\n' "$*"; }

# --- 1. Python venv -----------------------------------------------------------
say "Python venv"
# creates the environment, or rebuilds it if it's missing or broken (e.g. after a Python upgrade)
"$REPO/bin/gamedash-ensure-venv" || exit 1
"$VENV/bin/python" -m pip install --upgrade pip >/dev/null
"$VENV/bin/pip" install -q -r "$REPO/requirements.txt" && echo "Python libraries ready."

# --- 2. Data root -------------------------------------------------------------
say "Data root: $DATA"
mkdir -p "$DATA/certs" "$DATA/logs" "$BACKUPS"
chmod 700 "$DATA" "$DATA/certs" "$DATA/logs"
[ -f "$DATA/servers.json" ] || cp "$REPO/deploy/examples/servers.json.example" "$DATA/servers.json"
if [ ! -f "$DATA/secrets.conf" ]; then
    # Never start with the example's well-known placeholders: pick random passwords (letters and
    # digits only, which every game accepts). The owner can change them in Settings at any time.
    umask 077
    python3 - "$REPO/deploy/examples/secrets.conf.example" "$DATA/secrets.conf" <<'PW'
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
    echo "Picked random game passwords — see or change them in the dashboard (Settings → Game passwords)."
fi

# --- 3. Self-signed TLS cert --------------------------------------------------
say "TLS certificate"
if [ ! -f "$DATA/certs/cert.pem" ]; then
    HOSTN="$(hostname -f 2>/dev/null || hostname)"
    openssl req -x509 -newkey rsa:2048 -nodes -days 3650 \
        -keyout "$DATA/certs/key.pem" -out "$DATA/certs/cert.pem" \
        -subj "/CN=$HOSTN" \
        -addext "subjectAltName=DNS:$HOSTN,DNS:localhost,IP:127.0.0.1" 2>/dev/null
    chmod 600 "$DATA/certs/"*.pem
    echo "Self-signed cert generated (CN=$HOSTN, 10y). Browsers will warn once — expected."
fi

# --- 4. Dashboard admin password ---------------------------------------------
# The password is chosen in the browser on first visit (/setup), unlocked by a
# one-time code that install.sh prints at the end. Nothing to do here; to set it
# from the terminal instead:  gamedash reset-password
say "Dashboard admin password"
echo "Chosen in the browser on first visit, using the one-time setup code shown at the end."

# --- 5. systemd user units ----------------------------------------------------
say "systemd user units"
mkdir -p "$UNITS"
subst() { sed -e "s#__APP__#$APP#g" -e "s#__VENV__#$VENV#g" -e "s#__DATA__#$DATA#g" "$1"; }
subst "$REPO/deploy/systemd/gamedash.service.in"        > "$UNITS/gamedash.service"
subst "$REPO/deploy/systemd/gamedash-backup.service.in" > "$UNITS/gamedash-backup.service"
cp    "$REPO/deploy/systemd/gamedash-backup.timer"        "$UNITS/gamedash-backup.timer"
systemctl --user daemon-reload
systemctl --user enable --now gamedash.service
systemctl --user enable --now gamedash-backup.timer

# --- the "gamedash" command (gamedash help) ---------------------------------------
say "gamedash command"
mkdir -p "$HOME/.local/bin"
ln -sfn "$REPO/bin/gamedash" "$HOME/.local/bin/gamedash"
case ":$PATH:" in
    *":$HOME/.local/bin:"*) echo "installed: type  gamedash help" ;;
    *) echo "installed in ~/.local/bin — open a new terminal (or log in again), then type: gamedash help" ;;
esac

# --- 6. Linger (auto-start on boot without an active login) -------------------
say "Linger"
loginctl enable-linger "$USER" 2>/dev/null && echo "linger enabled" || \
    echo "Could not enable linger (try: sudo loginctl enable-linger $USER) — needed for boot auto-start."

# --- 7. Optional fail2ban -----------------------------------------------------
if [ "${1:-}" = "--fail2ban" ]; then
    say "fail2ban jail"
    sed "s#__GAMEDASH_LOGS__#$DATA/logs#" "$REPO/deploy/fail2ban/gamedash-jail.conf" | sudo tee /etc/fail2ban/jail.d/gamedash.conf >/dev/null
    sudo cp "$REPO/deploy/fail2ban/gamedash-filter.conf" /etc/fail2ban/filter.d/gamedash.conf
    sudo systemctl enable --now fail2ban && sudo systemctl restart fail2ban
fi

# When run by install.sh, its own final screen gives the address and setup code — don't repeat it.
[ "${GAMEDASH_FROM_INSTALLER:-0}" = 1 ] && exit 0
say "Done"
IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
echo "GameDash is running: https://${IP:-this-computer}:8443/   (the browser will warn about the certificate the first time — that is expected)"
if GAMEDASH_HOME="$DATA" "$VENV/bin/python" -c "import sys; sys.path.insert(0,'$APP'); import config; sys.exit(0 if config.needs_setup() else 1)" 2>/dev/null; then
    echo "First visit: you'll be asked for a one-time setup code. Get one with:  gamedash setup-code"
fi
echo "Then follow the Getting started checklist on the dashboard."
