#!/bin/bash
# gamedash-os-maintenance.sh — unattended OS patching for the game-server box.
#
# Runs as root from gamedash-os-maintenance.timer. The sequence is deliberately
# conservative, because this box hosts live game worlds:
#
#   1. Refuse to run if ANY player is online (checked via the dashboard's
#      unauthenticated public API). Deferring a week is always cheaper than
#      stranding someone mid-session.
#   2. Skip entirely if there is nothing to install and no reboot pending, so
#      quiet weeks never disturb the fleet.
#   3. Back up every server's saves before touching anything.
#   4. Stop the fleet GRACEFULLY (each unit's ExecStop does an in-game save —
#      ARK's RCON SaveWorld+DoExit needs time that a plain reboot won't give it).
#   5. Apply updates, keeping existing config files on conflict.
#   6. Reboot only if the kernel/libs actually require it; otherwise bring the
#      same servers back up immediately.
#
# INSTALL: this file must be owned by root and NOT writable by the game user —
# it runs as root on a timer, so a user-writable copy would be a root
# escalation. See install.md.
#
# Usage: gamedash-os-maintenance.sh [--dry-run]
set -uo pipefail

# Filled in by the install step in install.md (the account that runs GameDash).
GAME_USER="__GAME_USER__"
GAME_UID="__GAME_UID__"
case "$GAME_USER$GAME_UID" in *__*) echo "gamedash-os-maintenance: not configured — see install.md" >&2; exit 1 ;; esac
DASH_URL="https://127.0.0.1:8443/api/public.json"
GAMEDASH_HOME="/home/${GAME_USER}/.config/gamedash"
VENV_PY="/home/${GAME_USER}/gamedash/venv/bin/python"
BACKUPS_PY="/home/${GAME_USER}/gamedash/app/backups.py"
LOG="/var/log/gamedash-os-maintenance.log"
STOP_TIMEOUT=300          # seconds to wait for a graceful game-server stop
DRY_RUN=0
[ "${1:-}" = "--dry-run" ] && DRY_RUN=1

log() { printf '%s %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*" | tee -a "$LOG"; }
run() {
  if [ "$DRY_RUN" = 1 ]; then log "DRY-RUN would run: $*"; return 0; fi
  "$@"
}

# Run a command as the game user with access to its systemd --user instance.
as_user() {
  runuser -u "$GAME_USER" -- env \
    XDG_RUNTIME_DIR="/run/user/${GAME_UID}" \
    DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/${GAME_UID}/bus" \
    "$@"
}

log "=== OS maintenance run starting${DRY_RUN:+ (dry-run)} ==="

# --- 1. never interrupt live players -----------------------------------------
# Any failure to positively confirm "0 players" aborts: an unreachable dashboard
# means unknown state, and unknown must not mean "go ahead and reboot".
players="$(curl -sk --max-time 15 "$DASH_URL" 2>/dev/null | python3 -c '
import sys, json
try:
    d = json.load(sys.stdin)
    print(sum(s.get("players") or 0 for s in d.get("servers", [])))
except Exception:
    print("ERR")
' 2>/dev/null)"

if [ "$players" = "ERR" ] || [ -z "$players" ]; then
  log "ABORT: could not read player counts from $DASH_URL (dashboard down?). Deferring."
  exit 0
fi
if [ "$players" -gt 0 ] 2>/dev/null; then
  log "DEFER: $players player(s) online — not patching. Will retry next window."
  exit 0
fi
log "player check: 0 online, proceeding"

# --- 2. is there anything to do? ---------------------------------------------
export DEBIAN_FRONTEND=noninteractive
# Refreshing the package lists is non-destructive, so do it even on a dry run —
# otherwise the preview would count against stale lists and report "nothing to
# do" on a box whose auto-refresh is disabled (which is exactly this box).
apt-get update -qq >>"$LOG" 2>&1

plan="$(apt-get --just-print dist-upgrade 2>/dev/null | grep '^Inst ')"
pending="$(printf '%s' "$plan" | grep -c '^Inst ')"
reboot_pending=0
[ -f /var/run/reboot-required ] && reboot_pending=1

# A kernel in the plan means this run WILL end in a reboot. Worth knowing up
# front — /var/run/reboot-required only appears once the package is installed,
# so without this a --dry-run would report "no reboot required" for a run that
# is definitely going to reboot the box.
kernel_update=0
printf '%s\n' "$plan" | grep -qE '^Inst (linux-image|linux-generic)' && kernel_update=1
log "pending package updates: $pending; reboot already flagged: $reboot_pending; kernel in plan: $kernel_update"
if [ "$kernel_update" = 1 ]; then
  log "NOTE: kernel update included — this run will reboot the box when it finishes"
fi

if [ "$pending" -eq 0 ] && [ "$reboot_pending" -eq 0 ]; then
  log "nothing to do — fleet left running. Done."
  exit 0
fi

# --- 3. back up saves before touching anything -------------------------------
log "backing up all server saves…"
if run as_user env GAMEDASH_HOME="$GAMEDASH_HOME" "$VENV_PY" "$BACKUPS_PY" all >>"$LOG" 2>&1; then
  log "backups: ok"
else
  log "ABORT: save backup failed — refusing to patch without a good backup."
  exit 1
fi

# --- 4. stop the fleet gracefully --------------------------------------------
# Discover running game units rather than hardcoding, so servers added or
# removed via the dashboard are picked up automatically. gamedash.service (the
# dashboard) and the backup unit are not game servers — leave them alone.
mapfile -t UNITS < <(as_user systemctl --user list-units --state=running --no-legend 'gamedash-*.service' 2>/dev/null \
  | awk '{print $1}' | grep -vE '^gamedash-backup\.service$')

if [ "${#UNITS[@]}" -eq 0 ]; then
  log "no running game servers found"
else
  log "stopping ${#UNITS[@]} server(s): ${UNITS[*]}"
  for u in "${UNITS[@]}"; do
    log "  stopping $u"
    run as_user systemctl --user stop "$u"
  done
  # Confirm they are actually down before patching — ARK's graceful stop is slow
  # and patching mid-save is how worlds get corrupted.
  deadline=$(( SECONDS + STOP_TIMEOUT ))
  while [ "$SECONDS" -lt "$deadline" ]; do
    still="$(as_user systemctl --user is-active "${UNITS[@]}" 2>/dev/null | grep -c '^active$')"
    [ "$still" -eq 0 ] && break
    sleep 5
  done
  if [ "$DRY_RUN" = 0 ] && [ "${still:-0}" -ne 0 ]; then
    log "ABORT: $still server(s) still running after ${STOP_TIMEOUT}s — not patching. Restarting them."
    for u in "${UNITS[@]}"; do as_user systemctl --user start "$u"; done
    exit 1
  fi
  log "fleet down"
fi

# --- 5. apply updates --------------------------------------------------------
log "applying $pending package update(s)…"
if run apt-get -y \
      -o Dpkg::Options::=--force-confdef \
      -o Dpkg::Options::=--force-confold \
      dist-upgrade >>"$LOG" 2>&1; then
  log "dist-upgrade: ok"
else
  log "WARNING: dist-upgrade returned non-zero — check $LOG"
fi
run apt-get -y autoremove >>"$LOG" 2>&1
log "autoremove: done"

# --- 6. reboot if required, else bring the fleet back ------------------------
if [ -f /var/run/reboot-required ] || { [ "$DRY_RUN" = 1 ] && [ "$kernel_update" = 1 ]; }; then
  log "reboot required — rebooting now. Enabled servers will auto-start on boot."
  log "=== OS maintenance run complete (rebooting) ==="
  run systemctl reboot
  exit 0
fi

log "no reboot required — restarting ${#UNITS[@]} server(s)"
for u in "${UNITS[@]}"; do
  log "  starting $u"
  run as_user systemctl --user start "$u"
done
log "=== OS maintenance run complete ==="
