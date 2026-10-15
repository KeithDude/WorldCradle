#!/usr/bin/env python3
"""gamedash — command-line tools for the person who runs GameDash.

Usage: gamedash <command> [options]

  status                     Is the dashboard running, where to open it, and each server's state
  address                    The web addresses to open the dashboard at
  reset-password             Choose a new dashboard admin password (signs everyone out)
  setup-code                 A one-time code for choosing the first password in the browser
  start | stop | restart     Start, stop or restart the dashboard itself
  logs [N]                   The dashboard's last N log lines (default 50)

  servers                    List the game servers and whether they are running
  server start   <server>    Start a game server
  server stop    <server>    Stop a game server (asks first if players are online)
  server restart <server>    Restart a game server (asks first if players are online)
  server logs    <server> [N]  A game server's last N log lines (default 50)
  backup <server|all>        Back up a server's saves now ("all" = every server)

  check                      Quick health check: service, disk space, certificate, admin password
  version                    Which version of GameDash this is
  help                       This list

Server names are the short keys shown by "gamedash servers". Options may also be written
the old way: "gamedash -resetpassword" works the same as "gamedash reset-password".
"""
from __future__ import annotations

import getpass
import os
import shutil
import socket
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UNIT = "gamedash.service"


def _say(text: str = "") -> None:
    print(text, flush=True)


def _err(text: str) -> int:
    print(f"gamedash: {text}", file=sys.stderr)
    return 1


def _systemctl(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["systemctl", "--user", *args], capture_output=True, text=True, timeout=180)


def _active(unit: str) -> bool:
    return _systemctl("is-active", "--quiet", unit).returncode == 0


def _port() -> int:
    """The port the dashboard listens on, as written in its service file."""
    try:
        out = _systemctl("cat", UNIT).stdout
        import re
        m = re.search(r"--bind\s+\S*:(\d+)", out) or re.search(r":(\d{4,5})\b", out)
        return int(m.group(1)) if m else 8443
    except Exception:
        return 8443


def _lan_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("192.0.2.1", 9))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return ""


# ---- commands --------------------------------------------------------------------

def cmd_address(_args) -> int:
    import config
    port = _port()
    _say("Open GameDash in a web browser at:")
    ip = _lan_ip()
    if ip:
        _say(f"  on your home network:   https://{ip}:{port}/")
    host = config.load().get("public_host", "")
    if host:
        _say(f"  from anywhere:          https://{host}:{port}/   (if you forwarded port {port})")
    _say(f"  on this computer:       https://localhost:{port}/")
    return 0


def cmd_status(_args) -> int:
    import config
    running = _active(UNIT)
    _say(f"Dashboard: {'running' if running else 'NOT running — start it with: gamedash start'}")
    if config.needs_setup():
        _say("Admin password: not chosen yet — run: gamedash setup-code")
    _say()
    cmd_address(None)
    _say()
    return cmd_servers(None)


def cmd_reset_password(_args) -> int:
    import config
    _say("Choose a new admin password for the dashboard (at least 12 characters).")
    _say("Everyone currently signed in will be signed out.")
    try:
        pw = getpass.getpass("New password: ")
        again = getpass.getpass("Type it again: ")
    except (KeyboardInterrupt, EOFError):
        _say()
        return _err("cancelled — nothing changed")
    if pw != again:
        return _err("the two passwords don't match — nothing changed")
    if len(pw) < 12:
        return _err("too short: use at least 12 characters (this password guards full control "
                    "of your servers) — nothing changed")
    config.set_password(pw)
    _say("Done. Sign in to the dashboard with the new password.")
    return 0


def cmd_setup_code(_args) -> int:
    import config
    if not config.needs_setup():
        return _err("an admin password is already set. To choose a new one, run: gamedash reset-password")
    _say("Open the dashboard in your browser and enter this one-time code:")
    _say(f"  {config.new_setup_code()}")
    return 0


def _service(action: str) -> int:
    r = _systemctl(action, UNIT)
    if r.returncode != 0:
        return _err(f"couldn't {action} the dashboard: {(r.stderr or r.stdout).strip()}")
    _say(f"Dashboard {'stopped' if action == 'stop' else action + 'ed'}.")
    if action != "stop":
        cmd_address(None)
    return 0


def cmd_logs(args) -> int:
    n = args[0] if args and args[0].isdigit() else "50"
    r = subprocess.run(["journalctl", "--user", "-u", UNIT, "-n", n, "--no-pager", "-o", "short-iso"],
                       capture_output=True, text=True, timeout=60)
    _say(r.stdout.rstrip() or "(no log lines)")
    return 0


def cmd_servers(_args) -> int:
    from registry import by_key
    servers = list(by_key().values())
    if not servers:
        _say("No game servers yet — add one from the dashboard (Add a server).")
        return 0
    width = max(len(s.key) for s in servers)
    _say(f"{'SERVER':<{width}}  STATE     GAME")
    for s in sorted(servers, key=lambda s: s.key):
        state = "running" if _active(s.unit) else "stopped"
        _say(f"{s.key:<{width}}  {state:<8}  {s.name}")
    return 0


def _server(key: str):
    from registry import by_key
    s = by_key().get(key)
    if s is None:
        _err(f"no server called '{key}' — see: gamedash servers")
    return s


def cmd_server(args) -> int:
    if len(args) < 2:
        return _err("usage: gamedash server <start|stop|restart|logs> <server>")
    action, key = args[0].lower(), args[1]
    s = _server(key)
    if s is None:
        return 1
    if action == "logs":
        import controls
        n = int(args[2]) if len(args) > 2 and args[2].isdigit() else 50
        text = controls.read_logs(key, lines=max(n, 20)).rstrip()
        _say("\n".join(text.splitlines()[-n:]) or "(no log lines)")
        return 0
    if action not in ("start", "stop", "restart"):
        return _err("usage: gamedash server <start|stop|restart|logs> <server>")
    import controls
    try:
        r = controls.perform(key, action)
    except controls.ConfirmRequired as c:
        who = f": {', '.join(c.names)}" if c.names else ""
        _say(f"{c.players} player(s) are on {s.name}{who}.")
        if input(f"{action.capitalize()} it anyway? They will be disconnected. [y/N] ").strip().lower() != "y":
            return _err("cancelled — nothing changed")
        r = controls.perform(key, action, confirm=True)
    except controls.ActionError as e:
        return _err(str(e))
    _say(r.get("message") if isinstance(r, dict) and r.get("message") else f"{s.name}: {action} done.")
    return 0


def cmd_backup(args) -> int:
    if not args:
        return _err("usage: gamedash backup <server|all>")
    import backups
    if args[0] == "all":
        results = backups.backup_all()
        for key, result in results.items():
            _say(f"  {key}: {result}")
        failed = [k for k, v in results.items() if str(v).startswith("FAILED")]
        _say(f"{len(results) - len(failed)} of {len(results)} servers backed up.")
        return 1 if failed else 0
    if _server(args[0]) is None:
        return 1
    try:
        r = backups.create_backup(args[0], label="manual")
    except Exception as e:
        return _err(f"backup failed: {e}")
    _say(r.get("message", "Backup made.") if isinstance(r, dict) else "Backup made.")
    return 0


def cmd_check(_args) -> int:
    import config
    problems = 0
    def line(ok: bool, text: str):
        nonlocal problems
        problems += 0 if ok else 1
        _say(f"  {'OK     ' if ok else 'PROBLEM'}  {text}")
    _say("GameDash health check")
    line(_active(UNIT), "dashboard service running" if _active(UNIT) else "dashboard is not running — gamedash start")
    line(not config.needs_setup(), "admin password set" if not config.needs_setup()
         else "no admin password yet — gamedash setup-code")
    free = shutil.disk_usage(os.path.expanduser("~")).free / 2**30
    line(free >= 10, f"{free:.0f} GB free disk space" + ("" if free >= 10 else " — game servers need room to update"))
    cert = os.path.join(os.environ.get("GAMEDASH_HOME", os.path.expanduser("~/.config/gamedash")), "certs", "cert.pem")
    if os.path.isfile(cert):
        r = subprocess.run(["openssl", "x509", "-in", cert, "-noout", "-checkend", str(14 * 86400)],
                           capture_output=True, text=True)
        line(r.returncode == 0, "HTTPS certificate valid for at least 14 more days" if r.returncode == 0
             else "HTTPS certificate expires within 14 days")
    else:
        line(False, f"no HTTPS certificate found at {cert}")
    linger = subprocess.run(["loginctl", "show-user", os.environ.get("USER", ""), "-p", "Linger"],
                            capture_output=True, text=True).stdout.strip()
    line(linger.endswith("yes"), "starts with the computer (linger on)" if linger.endswith("yes")
         else "won't start with the computer — run: sudo loginctl enable-linger $USER")
    _say("All good." if problems == 0 else f"{problems} problem(s) found.")
    return 0 if problems == 0 else 1


def cmd_version(_args) -> int:
    r = subprocess.run(["git", "-C", REPO, "describe", "--always", "--dirty", "--tags"],
                       capture_output=True, text=True)
    _say(f"GameDash {r.stdout.strip() or '(version unknown)'}  —  {REPO}")
    return 0


def cmd_help(_args) -> int:
    _say(__doc__.strip())
    return 0


COMMANDS = {
    "status": cmd_status, "address": cmd_address, "url": cmd_address,
    "resetpassword": cmd_reset_password, "setpassword": cmd_reset_password, "password": cmd_reset_password,
    "setupcode": cmd_setup_code,
    "start": lambda a: _service("start"), "stop": lambda a: _service("stop"),
    "restart": lambda a: _service("restart"),
    "logs": cmd_logs, "log": cmd_logs,
    "servers": cmd_servers, "list": cmd_servers, "server": cmd_server,
    "backup": cmd_backup,
    "check": cmd_check, "doctor": cmd_check,
    "version": cmd_version, "help": cmd_help,
}


def main(argv: list[str]) -> int:
    if not argv:
        return cmd_help([])
    # "-resetpassword", "--reset-password", "reset_password" and "reset-password" all work
    name = argv[0].lstrip("-").replace("-", "").replace("_", "").lower()
    fn = COMMANDS.get(name)
    if fn is None:
        _err(f"unknown command '{argv[0]}'")
        return cmd_help([]) or 2
    try:
        return fn(argv[1:]) or 0
    except KeyboardInterrupt:
        _say()
        return 130


if __name__ == "__main__":
    import signal
    signal.signal(signal.SIGPIPE, signal.SIG_DFL)   # quiet when piped into head / less
    sys.exit(main(sys.argv[1:]))
