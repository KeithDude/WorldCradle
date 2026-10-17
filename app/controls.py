"""controls.py — admin actions on servers: start/stop through systemd, and the in-game
actions (save, message, kick, ban, chat) through each server's game type.

Start and Stop also decide whether a server starts with the computer: a server the owner
stopped stays stopped through a reboot, and one they started comes back.

Safety model (mirrors the operator's standing rule: never disrupt a server
without checking players first):
  * start / save / broadcast are non-disruptive.
  * stop / restart / force stop are disruptive — with players online the caller
    must pass confirm=True, and the LIVE player count is re-checked here
    regardless of the cached snapshot.
  * starting a server whose port-slot sibling is already running is refused
    (servers that share ports run one at a time).
"""
from __future__ import annotations

import os
import subprocess
import threading
import time

import alerts
import games
import monitor
from applog import app_log
from games.base import ActionError
from registry import Server, by_key

DISRUPTIVE = {"stop", "restart", "kill"}
# How long to hold back "server is down" alerts after GameDash itself takes a server down
QUIET_AFTER_STOP = 180
QUIET_AFTER_RESTART = 300
QUIET_DURING_UPDATE = 3600
VALID_ACTIONS = {"start", "stop", "restart", "kill", "save", "broadcast",
                 "kick", "ban", "chat"}


class ConfirmRequired(Exception):
    """Disruptive action blocked pending confirmation; carries player info."""
    def __init__(self, players: int, names: list[str]):
        self.players = players
        self.names = names
        super().__init__("confirmation required")


def _systemctl(action: str, unit: str) -> str:
    try:
        r = subprocess.run(
            ["systemctl", "--user", action, unit],
            capture_output=True, text=True, timeout=130,
        )
    except subprocess.TimeoutExpired:
        raise ActionError(f"The server took too long to {action} — give it a minute and check its status.")
    if r.returncode != 0:
        msg = (r.stderr or r.stdout or "").strip() or f"exit {r.returncode}"
        raise ActionError(f"Couldn't {action} the server: {msg}")
    return "ok"


def _starts_with_computer(s: Server, on: bool) -> None:
    """Whether the server starts by itself when the computer starts. It follows the owner's last
    Start / Stop, so a stopped server stays stopped through a reboot. Best effort: the start or
    stop itself has already happened, so a failure here is only logged."""
    try:
        r = subprocess.run(["systemctl", "--user", "enable" if on else "disable", s.unit],
                           capture_output=True, text=True, timeout=30)
        if r.returncode != 0:
            app_log.warning("couldn't %s %s at boot: %s", "enable" if on else "disable", s.unit,
                            (r.stderr or r.stdout).strip())
    except (OSError, subprocess.SubprocessError) as e:
        app_log.warning("couldn't change start-at-boot for %s: %s", s.unit, e)


def live_players(s: Server) -> tuple[int | None, list[str]]:
    """Best-effort LIVE player check (not the cached snapshot), via the game
    type's probe (fresh RCON/A2S/log/API query)."""
    game = games.get(s.kind)
    if game is None:
        return None, []
    try:
        p = game.probe(s)
        return p.get("players"), p.get("player_names", [])
    except Exception:
        return None, []


# ---- apply game updates (stop → steamcmd update → restart) -----------------
def _game_for_app(app: int):
    return next((g for g in games.all_types() if g.steam_app == app), None)


def _update_script(app: int) -> str | None:
    """Path of an operator-provided update script for this Steam app, if one
    exists in ~/Scripts (it takes precedence — it may carry local fixes).
    Without one, updates use the built-in steamcmd runner."""
    g = _game_for_app(app)
    if g and g.update_script:
        path = os.path.expanduser("~/Scripts/" + g.update_script)
        if os.path.isfile(path):
            return path
    return None


_update_lock = threading.Lock()
_update_job: dict = {"state": "idle"}  # state: idle|running|done|failed


def update_status() -> dict:
    with _update_lock:
        return dict(_update_job)


def start_update(app, confirm: bool = False) -> dict:
    """Apply a game update: check players, then async stop→update→restart.
    Raises ConfirmRequired if players are online and confirm is False."""
    try:
        app = int(app)
    except (TypeError, ValueError):
        raise ActionError("invalid app id")
    if _game_for_app(app) is None:
        raise ActionError("GameDash doesn't know how to update that game.")
    import installs
    if installs.status().get("state") == "running":
        raise ActionError("A game is being installed — wait for it to finish, then update.")
    with _update_lock:
        if _update_job.get("state") == "running":
            raise ActionError("an update is already running")

    servers = [s for s in by_key().values() if s.steam_app == app]
    if not servers:
        raise ActionError("no servers for that game")
    game = _game_for_app(app).label
    running = [s for s in servers if monitor.unit_active(s.unit)]

    # Player-check: updating stops the server(s).
    count = 0
    names: list[str] = []
    for s in running:
        c, n = live_players(s)
        if c:
            count += c
            names += n
    if count and not confirm:
        raise ConfirmRequired(count, names)

    with _update_lock:
        _update_job.clear()
        _update_job.update({"state": "running", "app": app, "game": game,
                            "step": "starting", "started_ts": time.time(),
                            "restart": [s.key for s in running]})
    threading.Thread(target=_run_update, args=(app, running, game),
                     name="update", daemon=True).start()
    return {"ok": True, "message": f"Update started for {game}."}


def _set_step_quiet(step: str):
    with _update_lock:           # progress ticks: update the status, don't spam the log
        _update_job["step"] = step


def _set_step(step: str):
    with _update_lock:
        _update_job["step"] = step
    app_log.info("update: %s", step)


def _run_update(app: int, running: list, game: str):
    try:
        # Stop running servers (suppress alerts; this is planned downtime).
        for s in running:
            alerts.suppress(s.key, QUIET_DURING_UPDATE)
        _set_step(f"stopping {len(running)} server(s)")
        for s in running:
            try:
                _systemctl("stop", s.unit)
            except ActionError as e:
                app_log.warning("update: stop %s failed: %s", s.unit, e)

        # Run the game's steamcmd update script.
        _set_step("running steamcmd update (may take several minutes)")
        script = _update_script(app)
        if script:
            r = subprocess.run(["bash", script], capture_output=True, text=True, timeout=3600)
            ok = r.returncode == 0
            tail = (r.stdout or "")[-300:].strip()
        else:
            import steam
            g = _game_for_app(app)
            install_dir = running[0].install_dir if running else next(
                (s.install_dir for s in by_key().values() if s.steam_app == app), "")
            ok, tail = steam.app_update(
                app, install_dir, g.steam_platform,
                lambda phase, pct: _set_step_quiet(f"{phase} {pct:.0f}%"), beta=g.steam_beta)
            tail = tail[-300:].strip()

        # Restart whatever was running before.
        _set_step(f"restarting {len(running)} server(s)")
        for s in running:
            try:
                _systemctl("start", s.unit)
            except ActionError as e:
                app_log.warning("update: start %s failed: %s", s.unit, e)

        with _update_lock:
            _update_job.update({
                "state": "done" if ok else "failed",
                "ok": ok, "finished_ts": time.time(),
                "message": (f"{game} updated and restarted." if ok
                            else f"{game} update FAILED (servers restarted on old build). {tail}"),
            })
        app_log.info("update %s: %s", game, "done" if ok else "FAILED")
        try:
            import updates
            updates.checker.trigger()  # refresh the up-to-date status
        except Exception:
            pass
    except Exception as e:
        app_log.exception("update %s crashed", game)
        for s in running:  # best-effort bring servers back
            try:
                _systemctl("start", s.unit)
            except Exception:
                pass
        with _update_lock:
            _update_job.update({"state": "failed", "ok": False,
                                "finished_ts": time.time(), "message": str(e)})


def read_logs(key: str, lines=300) -> str:
    """Recent log lines for a server. Prefers the game's own log file when it
    has one (log_path); otherwise reads the systemd journal for the unit
    (every server is a --user service)."""
    s = by_key().get(key)
    if s is None:
        raise ActionError("That server isn't on the dashboard any more — reload the page.")
    try:
        n = max(20, min(int(lines), 1000))
    except (TypeError, ValueError):
        n = 300

    if s.log_path and os.path.exists(s.log_path):
        text = monitor._tail_bytes(s.log_path, 256 * 1024)
        tail = "\n".join(text.splitlines()[-n:])
        return _redact(tail) or "(log file is empty)"

    try:
        r = subprocess.run(
            ["journalctl", "--user", "-u", s.unit, "-n", str(n),
             "--no-pager", "-o", "short-iso"],
            capture_output=True, text=True, timeout=15,
        )
    except Exception as e:
        raise ActionError(f"could not read journal: {e}")
    out = _redact((r.stdout or "").strip())
    return out or (r.stderr.strip() or "(no journal output for this unit)")


def _redact(text: str) -> str:
    """Blank out the game passwords wherever a server echoes them into its log
    (launch command lines, join requests). The log viewer never needs them, and
    the passwords page deliberately doesn't display them either."""
    import registry
    for value in set(registry.load_secrets().values()):
        if value and len(value) >= 4:
            text = text.replace(value, "••••••")
    return text


def _running_sibling(s: Server) -> Server | None:
    """A server sharing s's port-slot that is currently active, if any."""
    if not s.slot_group:
        return None
    for other in by_key().values():
        if other.key != s.key and other.slot_group == s.slot_group:
            if monitor.unit_active(other.unit):
                return other
    return None


def perform(key: str, action: str, message: str = "", confirm: bool = False,
            target: str = "") -> dict:
    """Execute an action. Raises ConfirmRequired / ActionError as needed.
    `target` is a player SteamID for kick/ban."""
    if action not in VALID_ACTIONS:
        raise ActionError(f"unknown action: {action}")
    s = by_key().get(key)
    if s is None:
        raise ActionError("That server isn't on the dashboard any more — reload the page.")

    game = games.get(s.kind)

    if action in ("kick", "ban"):
        if not game or not game.supports(action):
            raise ActionError(f"{s.name} doesn't support {action}.")
        target = (target or "").strip()
        if not target or not game.valid_target(target):
            raise ActionError("That doesn't look like a valid player to kick/ban.")
        resp = game.kick(s, target) if action == "kick" else game.ban(s, target)
        verb = "Kicked" if action == "kick" else "Banned"
        return {"ok": True, "message": f"{verb} player {target} on {s.name}: {resp}"}

    if action == "chat":
        if not game or not game.supports("chat"):
            raise ActionError(f"{s.name} has no live chat feed.")
        return {"ok": True, "chat": game.chat(s)}

    if action == "start":
        sib = _running_sibling(s)
        if sib is not None:
            raise ActionError(
                f"Can't start {s.name}: it shares ports with {sib.name}, "
                f"which is running. Stop {sib.name} first.")
        _systemctl("start", s.unit)
        _starts_with_computer(s, True)
        # servers sharing its ports must not also start with the computer
        for other in by_key().values():
            if other.key != s.key and s.slot_group and other.slot_group == s.slot_group:
                _starts_with_computer(other, False)
        return {"ok": True, "message": f"Started {s.name}."}

    if action in DISRUPTIVE:
        if not monitor.unit_active(s.unit):
            raise ActionError(f"{s.name} is not running.")
        count, names = live_players(s)
        if not confirm and count:  # players online and not yet confirmed
            raise ConfirmRequired(count, names)

    if action == "kill":
        alerts.suppress(s.key, QUIET_AFTER_RESTART)
        # Hard kill: SIGKILL the process so NO graceful ExecStop/save runs, then
        # stop to cancel Restart=on-failure (ExecStop now hits a dead process →
        # still no save), then clear the resulting 'failed' state.
        subprocess.run(["systemctl", "--user", "kill", "-s", "SIGKILL", s.unit],
                       capture_output=True, text=True, timeout=30)
        try:
            _systemctl("stop", s.unit)
        except ActionError:
            pass  # already dying; the kill is what matters
        subprocess.run(["systemctl", "--user", "reset-failed", s.unit],
                       capture_output=True, text=True, timeout=15)
        _starts_with_computer(s, False)
        return {"ok": True, "message": f"Force-stopped {s.name} — it was NOT saved."}

    if action in ("stop", "restart"):
        # Expected downtime — suppress the down/recovery alert for this server.
        alerts.suppress(s.key, QUIET_AFTER_RESTART if action == "restart" else QUIET_AFTER_STOP)
        _systemctl(action, s.unit)
        _starts_with_computer(s, action == "restart")    # stopped stays stopped through a reboot
        verb = "Stopped" if action == "stop" else "Restarted"
        return {"ok": True, "message": f"{verb} {s.name}."}

    if action == "save":
        if not game or not game.supports("save"):
            raise ActionError(f"{s.name} doesn't support a save command.")
        return {"ok": True, "message": f"Saved {s.name}: {game.save(s)}"}

    if action == "broadcast":
        if not game or not game.supports("broadcast"):
            raise ActionError(f"{s.name} doesn't support broadcast.")
        message = (message or "").strip()
        if not message:
            raise ActionError("Broadcast message is empty.")
        game.broadcast(s, message)
        return {"ok": True, "message": f"Broadcast sent to {s.name}."}

    raise ActionError(f"unhandled action: {action}")
