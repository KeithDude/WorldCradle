#!/usr/bin/env python3
"""gamedash — command-line tools for the person who runs GameDash.

Usage: gamedash <command> [options]

  status                     Is the dashboard running, where to open it, and each server's state
  address                    The web addresses to open the dashboard at
  qr                         A QR code to open the dashboard on a phone
  reset-password             Choose a new dashboard admin password (signs everyone out)
  setup-code                 A one-time code for choosing the first password in the browser
  passwords                  Show the game passwords (the one friends type to join, and the admin one)
  start | stop | restart     Start, stop or restart the dashboard itself
  logs [N]                   The dashboard's last N log lines (default 50)

  servers                    List the game servers and whether they are running
  server start   <server>    Start a game server
  server stop    <server>    Stop a game server (asks first if players are online)
  server restart <server>    Restart a game server (asks first if players are online)
  server logs    <server> [N]  A game server's last N log lines (default 50)
  backup <server|all>        Back up a server's saves now ("all" = every server)
  backup list <server>       A server's backups, newest first
  backup restore <server> <number>   Put a backup back (a safety copy is made first)
  unban <address>            Let an address that mistyped the password too often sign in again

  update                     Update GameDash itself (puts the old version back if the new one fails)
  uninstall                  Remove GameDash (asks before each step; never deletes games or saves)
  test-alert                 Send a test alert to every place alerts are set up to go
  check                      Quick health check: service, disk space, certificate, admin password
  version                    Which version of GameDash this is
  help                       This list

Server names are the short keys shown by "gamedash servers".
"""
from __future__ import annotations

import getpass
import os
import shutil
import socket
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("GAMEDASH_QUIET_LOG", "1")   # log lines still go to the log files, not the screen

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UNIT = os.environ.get("GAMEDASH_UNIT", "gamedash.service")   # overridable for testing


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


def cmd_passwords(args) -> int:
    """The two shared game passwords (join and admin)."""
    import registry
    sec = registry.load_secrets()
    join, admin = sec.get("GAME_SERVER_PASSWORD", ""), sec.get("GAME_ADMIN_PASSWORD", "")
    if "--join" in args:                      # just the join password (used by the installer)
        _say(join)
        return 0 if join else 1
    _say(f"Join password (give this to friends):   {join or '(not set)'}")
    _say(f"Admin password (keep this to yourself):  {admin or '(not set)'}")
    _say("Change them in the dashboard: Settings → Game passwords (then restart the servers).")
    return 0


def cmd_qr(_args) -> int:
    """A QR code of the home-network address, to open the dashboard on a phone."""
    ip = _lan_ip()
    if not ip:
        return _err("couldn't find this computer's home-network address")
    url = f"https://{ip}:{_port()}/"
    try:
        import segno
    except ImportError:
        return _err("the QR code needs the 'segno' package — run setup.sh again")
    _say(f"Scan with a phone on your home network to open {url}")
    segno.make(url, error="m").terminal(compact=True)
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
        return _err("usage: gamedash backup <server|all> | backup list <server> | backup restore <server> <backup>")
    import backups
    if args[0] == "list":
        if len(args) < 2:
            return _err("usage: gamedash backup list <server>")
        if _server(args[1]) is None:
            return 1
        items = backups.list_backups(args[1])
        if not items:
            _say("No backups yet for that server.")
            return 0
        import time
        for n, b in enumerate(items, 1):
            when = time.strftime("%Y-%m-%d %H:%M", time.localtime(b["mtime"]))
            _say(f"  {n:>2}. {when}  {b['size_h']:>8}  {b['name']}")
        _say("Restore one with: gamedash backup restore <server> <number>")
        return 0
    if args[0] == "restore":
        if len(args) < 3:
            return _err("usage: gamedash backup restore <server> <number or file name>")
        if _server(args[1]) is None:
            return 1
        key, which = args[1], args[2]
        items = backups.list_backups(key)
        name = items[int(which) - 1]["name"] if which.isdigit() and 0 < int(which) <= len(items) else which
        if not any(b["name"] == name for b in items):
            return _err(f"no backup '{which}' for that server — see: gamedash backup list {key}")
        s = _server(key)
        _say(f"This puts {s.name}'s saved world back to: {name}")
        _say("A safety copy of the current save is made first. If the server is running it is stopped,")
        _say("restored and started again.")
        if not _yes("Restore it?"):
            return _err("cancelled — nothing changed")
        import controls
        try:
            r = backups.restore_backup(key, name)
        except controls.ConfirmRequired as c:
            _say(f"{c.players} player(s) are on {s.name}" + (f": {', '.join(c.names)}" if c.names else "") + ".")
            if not _yes("Restore anyway? They will be disconnected."):
                return _err("cancelled — nothing changed")
            r = backups.restore_backup(key, name, confirm=True)
        except controls.ActionError as e:
            return _err(str(e))
        _say(r.get("message", "Restored."))
        return 0
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


def _git(*args: str, check: bool = True) -> str:
    r = subprocess.run(["git", "-C", REPO, *args], capture_output=True, text=True, timeout=300)
    if check and r.returncode != 0:
        raise RuntimeError((r.stderr or r.stdout).strip() or f"git {' '.join(args)} failed")
    return r.stdout.strip()


def _answers(timeout: int = 60) -> bool:
    """Does the dashboard answer over HTTPS within `timeout` seconds?"""
    import ssl
    import time
    import urllib.request
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE                 # self-signed certificate is normal here
    end = time.time() + timeout
    while time.time() < end:
        try:
            with urllib.request.urlopen(f"https://127.0.0.1:{_port()}/api/public.json", context=ctx, timeout=5) as r:
                if r.status == 200:
                    return True
        except Exception:
            pass
        time.sleep(2)
    return False


def _install_requirements() -> None:
    pip = os.path.join(REPO, "venv", "bin", "pip")
    r = subprocess.run([pip, "install", "-q", "-r", os.path.join(REPO, "requirements.txt")],
                       capture_output=True, text=True, timeout=1200)
    if r.returncode != 0:
        raise RuntimeError("installing the Python libraries failed:\n" + (r.stderr or r.stdout).strip()[-1500:])


def _self_test() -> None:
    """The new code must at least load: the web app, every game type and every page."""
    py = os.path.join(REPO, "venv", "bin", "python")
    code = ("import sys; sys.path.insert(0, '.'); import app, games\n"
            "[ (g.port_fields(), g.extra_fields) for g in games.all_types() if g.kind != 'custom' ]\n"
            "[ app.app.jinja_env.get_template(t) for t in ('admin.html', 'public.html', 'base.html', 'login.html') ]")
    r = subprocess.run([py, "-c", code], cwd=os.path.join(REPO, "app"), capture_output=True, text=True, timeout=120)
    if r.returncode != 0:
        raise RuntimeError("the new version doesn't load:\n" + (r.stderr or r.stdout).strip()[-1500:])


def cmd_update(args) -> int:
    """Update GameDash itself from its home repository; roll back if the new version fails."""
    if not os.path.isdir(os.path.join(REPO, ".git")):
        return _err("this copy of GameDash wasn't installed with git, so it can't update itself. "
                    "Download the new version and run install.sh again.")
    if _git("status", "--porcelain"):
        return _err("GameDash's files have been changed on this computer, so updating could lose those "
                    "changes. Nothing was done.")
    branch = _git("rev-parse", "--abbrev-ref", "HEAD")
    _say("Checking for a new version…")
    try:
        _git("fetch", "--quiet", "origin", branch)
    except RuntimeError as e:
        return _err(f"couldn't reach GameDash's home on the internet: {e}")
    old = _git("rev-parse", "HEAD")
    new = _git("rev-parse", f"origin/{branch}")
    if old == new:
        _say("GameDash is up to date.")
        return 0
    if subprocess.run(["git", "-C", REPO, "merge-base", "--is-ancestor", old, new]).returncode != 0:
        return _err("this copy has commits that aren't in the published version — not updating automatically.")
    _say("What's new:")
    for line in _git("log", "--oneline", "--no-decorate", f"{old}..{new}").splitlines()[:30]:
        _say(f"  • {line.split(' ', 1)[1] if ' ' in line else line}")
    if "--yes" not in args and "-y" not in args:
        try:
            if input("Update now? The dashboard restarts (game servers keep running). [Y/n] ").strip().lower() in ("n", "no"):
                return _err("cancelled — nothing changed")
        except EOFError:
            pass

    def rollback(reason: str) -> int:
        _say(f"Problem: {reason}")
        _say("Putting the previous version back…")
        try:
            _git("reset", "--hard", "--quiet", old)
            _install_requirements()
            _systemctl("restart", UNIT)
        except Exception as e:
            return _err(f"rolling back also failed ({e}). Run: git -C {REPO} reset --hard {old[:12]} "
                        "and then: gamedash restart")
        _say("The previous version is running again." if _answers() else
             "The previous version is back, but the dashboard isn't answering yet — check: gamedash logs")
        return 1

    try:
        _say("Downloading…")
        _git("merge", "--ff-only", "--quiet", new)
        _say("Installing libraries…")
        _install_requirements()
        _say("Checking the new version…")
        _self_test()
    except Exception as e:
        return rollback(str(e))
    _say("Restarting the dashboard…")
    _systemctl("restart", UNIT)
    if not _answers():
        return rollback("the new version started but isn't answering")
    _say(f"Updated to {new[:7]}. The dashboard is running.")
    return 0


def _yes(question: str, default: bool = False) -> bool:
    hint = "[Y/n]" if default else "[y/N]"
    try:
        answer = input(f"{question} {hint} ").strip().lower()
    except EOFError:
        return default
    return default if not answer else answer in ("y", "yes")


def cmd_uninstall(args) -> int:
    """Remove GameDash from this computer, step by step, asking before anything that can't be undone.
    Game installs and saves are never deleted; backups and settings only if asked."""
    import config
    from registry import by_key
    home = os.path.expanduser("~")
    data = os.environ.get("GAMEDASH_HOME", os.path.join(home, ".config", "gamedash"))
    backups = os.environ.get("GAMEDASH_BACKUPS", os.path.join(home, ".local", "share", "gamedash", "backups"))
    units_dir = os.path.join(home, ".config", "systemd", "user")
    servers = sorted(by_key().values(), key=lambda s: s.key)
    running = [s for s in servers if _active(s.unit)]
    # where the games live — read now, while the settings still exist
    installs = sorted({config.install_dir(s.kind) for s in servers if s.kind != "custom"})

    _say("This removes GameDash from this computer.")
    _say("Your games and their saved worlds are NOT deleted. You'll be asked about anything else.")
    _say()
    if input('Type "uninstall" to continue: ').strip().lower() != "uninstall":
        return _err("cancelled — nothing changed")

    # 1. game servers GameDash manages: they are background services that would otherwise keep running
    if servers:
        _say()
        _say(f"GameDash manages {len(servers)} game server(s)" + (f", {len(running)} running now" if running else "") + ":")
        for s in servers:
            _say(f"  {s.key:<16} {s.name}")
        if _yes("Stop them and remove them from the computer's start-up? (Their games and saves stay on disk.)", True):
            import controls
            for s in running:
                try:
                    who = controls.live_players(s)[0]
                except Exception:
                    who = None
                if who:
                    _say(f"  {s.name} has {who} player(s) online.")
                    if not _yes(f"  Stop {s.name} anyway?"):
                        _say(f"  Left {s.name} running.")
                        continue
            for s in servers:
                _systemctl("disable", "--now", s.unit)
                path = os.path.join(units_dir, s.unit)
                if os.path.basename(path).startswith("gamedash-") and os.path.isfile(path):
                    os.remove(path)
                _say(f"  removed {s.unit}")

    # 2. the dashboard itself
    _say()
    for unit in ("gamedash-backup.timer", "gamedash-backup.service", UNIT, "gamedash-cert-renew.timer",
                 "gamedash-cert-renew.service"):
        _systemctl("disable", "--now", unit)
        path = os.path.join(units_dir, unit)
        if os.path.isfile(path):
            os.remove(path)
    _systemctl("daemon-reload")
    link = os.path.join(home, ".local", "bin", "gamedash")
    if os.path.islink(link):
        os.remove(link)
    _say("Removed the dashboard service, the daily backup timer and the gamedash command.")

    # 3. settings (dashboard password, game passwords, server list, certificate) — ask
    if os.path.isdir(data) and _yes(f"Delete GameDash's settings too ({data})? This includes the game passwords."):
        shutil.rmtree(data, ignore_errors=True)
        _say("Settings deleted.")
    elif os.path.isdir(data):
        _say(f"Kept the settings in {data} (installing GameDash again will use them).")

    # 4. backups — they hold copies of saves, so ask separately and default to keeping them
    if os.path.isdir(backups) and os.listdir(backups):
        size = sum(os.path.getsize(os.path.join(dp, f)) for dp, _, fs in os.walk(backups) for f in fs) / 2**30
        if _yes(f"Delete the save backups too ({backups}, {size:.1f} GB)? They can't be recovered."):
            shutil.rmtree(backups, ignore_errors=True)
            _say("Backups deleted.")
        else:
            _say(f"Kept the backups in {backups}.")

    # 5. what is left and how to finish
    _say()
    _say("Done. Still on this computer, on purpose:")
    _say(f"  • the GameDash program folder: {REPO}  — delete it with:  rm -rf {REPO}")
    if installs:
        _say("  • your games and saves: " + ", ".join(installs))
    if os.path.isfile("/etc/fail2ban/jail.d/gamedash.conf"):
        _say("  • the login-protection rule: sudo rm /etc/fail2ban/jail.d/gamedash.conf "
             "/etc/fail2ban/filter.d/gamedash.conf && sudo systemctl reload fail2ban")
    _say("  • system packages installed for the games (Wine, Java, …): remove with apt if you no longer need them.")
    return 0


def cmd_unban(args) -> int:
    """Lift a block on an address that mistyped the dashboard password too often."""
    import ipaddress
    if not args:
        return _err("usage: gamedash unban <address>   (the address shown in: gamedash logs)")
    try:
        ip = str(ipaddress.ip_address(args[0]))
    except ValueError:
        return _err(f"'{args[0]}' isn't an address like 203.0.113.7")
    done = False
    if shutil.which("fail2ban-client") and os.path.isfile("/etc/fail2ban/jail.d/gamedash.conf"):
        _say("Removing the block in fail2ban (this needs your computer's admin password)…")
        r = subprocess.run(["sudo", "fail2ban-client", "set", "gamedash", "unbanip", ip])
        done = r.returncode == 0
    # the dashboard's own short lock-out after wrong passwords is kept in memory: a restart clears it
    _systemctl("restart", UNIT)
    _say(f"{ip} can try to sign in again." if done or not shutil.which("fail2ban-client")
         else f"The dashboard's own lock-out is cleared; fail2ban may still be blocking {ip}.")
    return 0


def cmd_test_alert(_args) -> int:
    """Send a test alert to every place alerts are set up to go."""
    import alerts
    results = alerts.send_test()
    if not results:
        return _err("no alerts are set up yet — add one in the dashboard: Settings → Alerts")
    for r in results:
        _say(f"  {'✅' if r['ok'] else '❌'} {r['service']}: " + ("sent — check it arrived" if r["ok"] else r["error"]))
    return 0 if all(r["ok"] for r in results) else 1


def cmd_version(_args) -> int:
    from version import version
    r = subprocess.run(["git", "-C", REPO, "describe", "--always", "--dirty", "--tags"],
                       capture_output=True, text=True)
    build = f" (build {r.stdout.strip()})" if r.returncode == 0 and r.stdout.strip() else ""
    _say(f"GameDash {version()}{build}  —  {REPO}")
    return 0


def cmd_help(_args) -> int:
    _say(__doc__.strip())
    return 0


COMMANDS = {
    "status": cmd_status, "address": cmd_address, "url": cmd_address, "qr": cmd_qr,
    "resetpassword": cmd_reset_password, "setpassword": cmd_reset_password, "password": cmd_reset_password,
    "setupcode": cmd_setup_code, "passwords": cmd_passwords,
    "start": lambda a: _service("start"), "stop": lambda a: _service("stop"),
    "restart": lambda a: _service("restart"),
    "logs": cmd_logs, "log": cmd_logs,
    "servers": cmd_servers, "list": cmd_servers, "server": cmd_server,
    "backup": cmd_backup,
    "check": cmd_check, "doctor": cmd_check, "update": cmd_update, "upgrade": cmd_update,
    "uninstall": cmd_uninstall, "remove": cmd_uninstall, "unban": cmd_unban,
    "testalert": cmd_test_alert,
    "version": cmd_version, "help": cmd_help,
}


def main(argv: list[str]) -> int:
    if not argv:
        return cmd_help([])
    # forgiving about spelling: "reset-password", "reset_password" and "resetpassword" all work
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
