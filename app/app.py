"""app.py — game-server dashboard web app.

Two tiers:
  * Public (no login): each server's online/offline + player count only.
  * Admin (login):      full detail (names, resources, ports, box) + controls.

The background poller refreshes a cached fleet snapshot; requests read the cache.
"""
from __future__ import annotations

import functools
import re
import secrets
import subprocess
import threading
import time

from flask import (Flask, g, jsonify, redirect, render_template, request,
                   send_file, session, url_for)
from werkzeug.exceptions import HTTPException

import alerts
import backups
import certs
import config
import controls
import games
import installs
import monitor
import notifiers
import osupdates
import ports
import project
import provision
import reach
import registry
import updates
import version
from applog import access_log, app_log, audit_log
from poller import poller

cfg = config.load()

# The footer's "support the developer" link; only ever a plain https address.
_SUPPORT_URL = project.SUPPORT_URL if re.match(r"^https://[^\s\"'<>]+$", project.SUPPORT_URL or "") else ""

app = Flask(__name__)
app.secret_key = cfg["secret_key"]
# Preserve our server ordering (sorted by game/world) in JSON responses;
# Flask's jsonify sorts dict keys alphabetically by default, which would
# reorder the admin feed's servers object on the client re-render.
app.json.sort_keys = False
app.config.update(
    # "__Host-" makes browsers refuse the cookie unless it is Secure, has
    # Path=/ and no Domain — it can't be set or overridden from another host.
    SESSION_COOKIE_NAME="__Host-gamedash",
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=True,   # cookie only sent over HTTPS (we serve TLS)
    PERMANENT_SESSION_LIFETIME=60 * 60 * 12,  # 12h
    # Largest legitimate body is a launch script (64 KB); nothing uploads files.
    MAX_CONTENT_LENGTH=256 * 1024,
)


@app.before_request
def _csp_nonce():
    # Per-response nonce: the only inline <script> blocks allowed to run are the
    # ones our own templates emit with it (see templates: nonce="{{ csp_nonce }}").
    g.csp_nonce = secrets.token_urlsafe(16)


_CERT_RECHECK_SECONDS = 300
_cert_seen = {"ts": 0.0, "trusted": False}


def _cert_trusted() -> bool:
    """Is a CA-issued certificate being served? (cached — it's read on every page)"""
    if time.time() - _cert_seen["ts"] > _CERT_RECHECK_SECONDS:
        _cert_seen.update(ts=time.time(), trusted=certs.info()["trusted"])
    return _cert_seen["trusted"]


@app.context_processor
def _template_values():
    return {"csp_nonce": getattr(g, "csp_nonce", ""), "game_titles": games.titles(),
            "cert_trusted": _cert_trusted(), "project_url": project.PROJECT_URL,
            "support_url": _SUPPORT_URL, "support_label": project.SUPPORT_LABEL,
            "gd_version": version.version()}


@app.after_request
def _security_headers(resp):
    # This is expected to be reachable from the internet — set strict headers.
    nonce = getattr(g, "csp_nonce", "")
    resp.headers.setdefault("Content-Security-Policy", "; ".join([
        "default-src 'self'",
        f"script-src 'self' 'nonce-{nonce}'",   # no inline handlers, no eval
        "style-src 'self' 'unsafe-inline'",     # small style= attributes in the UI
        "img-src 'self' data:",
        "connect-src 'self'",
        "object-src 'none'",
        "base-uri 'none'",
        "form-action 'self'",
        "frame-ancestors 'none'",
    ]))
    resp.headers.setdefault("Strict-Transport-Security", "max-age=31536000")
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("X-Frame-Options", "DENY")
    resp.headers.setdefault("Referrer-Policy", "same-origin")
    resp.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
    resp.headers.setdefault("Permissions-Policy",
                            "camera=(), microphone=(), geolocation=(), payment=(), usb=()")
    # Admin pages/feeds carry ports, player names and paths — keep them out of
    # browser and proxy caches.
    if request.path.startswith(("/admin", "/api/admin", "/login", "/setup")):
        resp.headers["Cache-Control"] = "no-store"
    return resp


# High-frequency poll endpoints — log them only when something's off (e.g. a
# 401 from an unauthenticated hit), not on every 5s heartbeat.
_QUIET_PATHS = {"/api/public.json", "/api/admin.json"}


@app.after_request
def _access_log(resp):
    path = request.path
    if path.startswith("/static/"):
        return resp  # skip asset noise
    if path in _QUIET_PATHS and resp.status_code in (200, 304):
        return resp  # suppress only the normal polling heartbeat (log auth-redirects/errors)
    access_log.info('%s "%s %s" %s ua="%s"', _client_ip(), request.method, path,
                    resp.status_code, request.user_agent.string[:90])
    return resp

# ---- login rate limiting (in-memory, per source IP) ------------------------
_LOCK_AFTER = 5          # failed attempts
_LOCK_SECONDS = 300      # lockout window
_attempts: dict[str, list[float]] = {}
_attempts_lock = threading.Lock()
_MAX_TRACKED_IPS = 10_000   # bound memory under a wide spray of source IPs


def _client_ip() -> str:
    return request.remote_addr or "unknown"


def _dashboard_port() -> int:
    """The port this page was opened on (set in gamedash.service, normally 8443)."""
    _, _, port = request.host.rpartition(":")
    return int(port) if port.isdigit() else 443


def _command_succeeds(args) -> bool:
    try:
        return subprocess.run(args, capture_output=True, text=True, timeout=5).returncode == 0
    except Exception:
        return False


def _locked_out(ip: str) -> int:
    """Return remaining lockout seconds (0 if not locked)."""
    now = time.time()
    with _attempts_lock:
        fails = [t for t in _attempts.get(ip, []) if now - t < _LOCK_SECONDS]
        if fails:
            _attempts[ip] = fails
        else:
            _attempts.pop(ip, None)
        if len(fails) >= _LOCK_AFTER:
            return int(_LOCK_SECONDS - (now - fails[0]))
    return 0


def _record_fail(ip: str) -> None:
    now = time.time()
    with _attempts_lock:
        if len(_attempts) >= _MAX_TRACKED_IPS:   # drop IPs whose window has expired
            for k in [k for k, v in _attempts.items() if not v or now - v[-1] >= _LOCK_SECONDS]:
                del _attempts[k]
            if len(_attempts) >= _MAX_TRACKED_IPS:   # still full → drop the oldest half
                for k in sorted(_attempts, key=lambda k: _attempts[k][-1])[:_MAX_TRACKED_IPS // 2]:
                    del _attempts[k]
        _attempts.setdefault(ip, []).append(now)


def _clear_fails(ip: str) -> None:
    with _attempts_lock:
        _attempts.pop(ip, None)


# ---- auth ------------------------------------------------------------------

# Admin routes a browser opens as a page (or a download link). Signed out, these go to the
# login page; every other admin route is called by the page's script, which gets a 401 and
# then goes to the login page itself — a redirect would just hand it a page it can't read.
_PAGE_ENDPOINTS = {"admin", "admin_settings", "backups_page", "admin_backup_download"}


def login_required(view):
    @functools.wraps(view)
    def wrapped(*a, **kw):
        # "av" ties the session to the credentials it was issued under: a
        # password change (or secret-key rotation) signs every session out.
        if not session.get("admin") or not secrets.compare_digest(
                str(session.get("av", "")), config.auth_version()):
            session.clear()
            if request.method == "GET" and request.endpoint in _PAGE_ENDPOINTS:
                return redirect(url_for("login", next=request.path))
            return jsonify({"ok": False, "error": "Signed out — sign in again."}), 401
        return view(*a, **kw)
    return wrapped


def csrf_token() -> str:
    tok = session.get("csrf")
    if not tok:
        tok = secrets.token_urlsafe(32)
        session["csrf"] = tok
    return tok


def csrf_ok() -> bool:
    sent = request.headers.get("X-CSRF-Token", "")
    good = session.get("csrf", "")
    return bool(good) and secrets.compare_digest(sent, good)


CSRF_STALE = "This page has been open a while and needs refreshing — reload it and try again."


def csrf_required(view):
    """Refuse a POST that doesn't carry this page's CSRF token. Goes under @login_required.
    (tests/test_app_routes.py checks that every admin POST route has it.)"""
    @functools.wraps(view)
    def wrapped(*a, **kw):
        if request.method == "POST" and not csrf_ok():
            audit_log.warning("%s rejected (bad CSRF) ip=%s", request.path, _client_ip())
            return jsonify({"ok": False, "error": CSRF_STALE}), 403
        return view(*a, **kw)
    return wrapped


def _start_admin_session() -> None:
    session.clear()   # start from a fresh session (drops any pre-login state)
    session["admin"] = True
    # "av" ties the session to the current password; see login_required
    session["av"] = config.auth_version()
    session.permanent = True


# ---- data shaping ----------------------------------------------------------

def _public_servers(snap: dict) -> list[dict]:
    """Minimal, public-safe projection: no names, ports, resources, or IPs."""
    out = []
    for v in snap.get("servers", {}).values():
        out.append({
            "name": v["name"],
            "kind": v["kind"],
            "server_name": v["server_name"],   # actual in-game name (helps players find it)
            "join_port": v["join_port"],       # how to connect (host:port)
            "online": v["online"],
            "players": v["players"],          # int or null (unknown)
            "rows": {"players": v.get("rows", {}).get("players", False)},
            "max_players": v["max_players"],
        })
    return out


# ---- routes ----------------------------------------------------------------

@app.route("/")
def index():
    snap = poller.snapshot()
    servers = _public_servers(snap)
    online = sum(1 for s in servers if s["online"])
    return render_template("public.html", servers=servers,
                           online=online, total=len(servers))


@app.route("/api/public.json")
def api_public():
    snap = poller.snapshot()
    return jsonify({"servers": _public_servers(snap), "ts": snap.get("ts", 0),
                    "titles": games.titles(),
                    "join_steps": games.join_steps(),
                    "public_host": config.load().get("public_host", "")})


@app.route("/setup", methods=["GET", "POST"])
def setup():
    """First run only: whoever holds the installer's one-time code chooses the
    admin password. Unavailable the moment a password exists."""
    if not config.needs_setup():
        return redirect(url_for("login"))
    ip = _client_ip()
    error = None
    has_code = bool(config.load().get("setup_code"))
    if request.method == "POST" and has_code:
        pw, pw2 = request.form.get("password", ""), request.form.get("password2", "")
        wait = _locked_out(ip)
        if wait > 0:
            audit_log.warning("setup blocked (locked out) ip=%s", ip)
            error = f"Too many attempts. Try again in {wait}s."
        elif not config.check_setup_code(request.form.get("code", "")):
            _record_fail(ip)
            audit_log.warning("login FAILED ip=%s", ip)   # same line fail2ban watches
            error = "That setup code isn't right. Check it against what the installer printed."
        elif len(pw) < config.MIN_ADMIN_PASSWORD:
            error = f"Please choose a password of at least {config.MIN_ADMIN_PASSWORD} characters."
        elif pw != pw2:
            error = "The two passwords don't match — type them again."
        else:
            config.set_password(pw)       # also retires the setup code
            _clear_fails(ip)
            _start_admin_session()
            audit_log.info("first-run setup completed ip=%s", ip)
            return redirect(url_for("admin"))
    return render_template("setup.html", error=error, has_code=has_code), (401 if error else 200)


@app.route("/admin/checklist", methods=["GET", "POST"])
@login_required
@csrf_required
def admin_checklist():
    if request.method == "POST":
        hide = bool((request.get_json(silent=True) or {}).get("hidden", True))
        config.update(lambda c: c.__setitem__("checklist_hidden", hide))
    cfg = config.load()
    sec = registry.load_secrets()
    placeholder = {"", "change-me-join", "change-me-admin"}
    servers = registry.load_servers()
    items = [
        {"id": "password", "done": True, "title": "Create your admin password",
         "help": "Done — that's the password you signed in with."},
        {"id": "gamepw", "title": "Choose your game passwords", "go": "/admin/settings#passwords",
         "done": sec.get("GAME_SERVER_PASSWORD", "") not in placeholder
                 and sec.get("GAME_ADMIN_PASSWORD", "") not in placeholder,
         "help": "One password your friends type to join, and a private one that makes you the "
                 "admin. Set them before creating servers."},
        {"id": "install", "title": "Install a game", "go": "#games-panel",
         "done": any(g["installed"] for g in installs.catalog()),
         "help": "Open “Games” below and press Install next to the game you want to host."},
        {"id": "server", "title": "Add your first server", "go": "#add-panel",
         "done": bool(servers),
         "help": "Open “Add a server”, pick the game, give it a name and press Add server."},
        {"id": "address", "title": "Tell GameDash your public address", "go": "/admin/settings",
         "done": bool(cfg.get("public_host")),
         "help": "The address your friends connect to, shown in each server's “How to join”. "
                 "Settings → General."},
        {"id": "reach", "title": "Check that friends can connect", "done": None,
         "help": "On a running server's card press “Can friends connect?” — it lists the router "
                 "ports to open and tests whether the server can be reached."},
        {"id": "alerts", "title": "Get told when something goes wrong (optional)",
         "go": "/admin/settings#alerts", "done": bool(alerts.destinations(cfg)),
         "help": "Send a message to your phone or a Discord channel if a server goes down or a "
                 "backup fails."},
    ]
    required_done = all(i["done"] for i in items if i["id"] in ("gamepw", "install", "server"))
    return jsonify({"ok": True, "items": items, "hidden": bool(cfg.get("checklist_hidden")),
                    "all_done": required_done})


@app.route("/login", methods=["GET", "POST"])
def login():
    if config.needs_setup():
        return redirect(url_for("setup"))
    ip = _client_ip()
    error = None
    if request.method == "POST":
        wait = _locked_out(ip)
        if wait > 0:
            audit_log.warning("login blocked (locked out) ip=%s", ip)
            error = f"Too many attempts. Try again in {wait}s."
        elif config.check_password(request.form.get("password", "")):
            _clear_fails(ip)
            _start_admin_session()
            audit_log.info("login success ip=%s", ip)
            nxt = request.args.get("next") or url_for("admin")
            # open-redirect guard: must be a site-relative path, not "//host"
            # or "/\host" (protocol-relative URLs browsers treat as external).
            if not nxt.startswith("/") or nxt.startswith(("//", "/\\")):
                nxt = url_for("admin")
            return redirect(nxt)
        else:
            _record_fail(ip)
            audit_log.warning("login FAILED ip=%s", ip)
            error = "Incorrect password."
    return render_template("login.html", error=error), (401 if error else 200)


@app.route("/logout", methods=["POST"])
def logout():
    if session.get("admin"):
        audit_log.info("logout ip=%s", _client_ip())
    session.clear()
    return redirect(url_for("index"))


@app.route("/admin")
@login_required
def admin():
    snap = poller.snapshot()
    return render_template("admin.html", snap=snap, csrf=csrf_token())


@app.route("/api/admin.json")
@login_required
def api_admin():
    snap = dict(poller.snapshot())
    # update status is keyed by Steam app id; JSON keys must be strings
    snap["updates"] = {str(k): v for k, v in updates.checker.snapshot().items()}
    snap["os_updates"] = osupdates.checker.snapshot()
    snap["update_job"] = controls.update_status()
    snap["provision_job"] = provision.provision_status()
    snap["install_job"] = installs.status()
    snap["public_host"] = config.load().get("public_host", "")
    snap["titles"] = games.titles()
    snap["join_steps"] = games.join_steps()
    return jsonify(snap)


@app.route("/admin/settings")
@login_required
def admin_settings():
    return render_template("settings.html", csrf=csrf_token())


@app.route("/admin/backups")
@login_required
def backups_page():
    snap = poller.snapshot()
    return render_template("backups.html", snap=snap, csrf=csrf_token())


# What the settings forms accept. Paths and the name prefix end up in generated launch
# scripts, so they are limited to characters that can't break out of them.
_HOST_RE = re.compile(r"^[A-Za-z0-9]([A-Za-z0-9.-]{0,251}[A-Za-z0-9])?$")  # hostname or IP only
_PATH_RE = re.compile(r"^(~|/)[A-Za-z0-9._/\-]{0,300}$")   # absolute or ~-relative, no shell metachars
_CLUSTER_ID_RE = re.compile(r"^[A-Za-z0-9_]{1,40}$")
_NAME_PREFIX_RE = re.compile(r"^[A-Za-z0-9 _.\-\[\]()]{0,30}$")
_PW_RE = re.compile(r"^[A-Za-z0-9!@#%^&*()_+\-=:.,]{1,64}$")  # shell- & ARK-option-safe


def _settings_changes(data: dict, current: dict) -> tuple[dict, list[str]]:
    """The settings the form changed, checked. Returns (changes, errors)."""
    changes, errors = {}, []
    if "public_host" in data:
        host = str(data["public_host"]).strip()
        # shown to every visitor as the join address
        if host and not _HOST_RE.match(host):
            errors.append("public host: a hostname or IP address only (no scheme, port or path)")
        else:
            changes["public_host"] = host
    if "secrets_conf" in data and str(data["secrets_conf"]).strip():
        path = str(data["secrets_conf"]).strip()
        if not _PATH_RE.match(path):
            errors.append("secrets file: plain path characters only (letters, digits, / . _ - ~)")
        else:
            changes["secrets_conf"] = path
    if "ark_cluster_id" in data:
        cluster = str(data["ark_cluster_id"]).strip()
        if cluster and not _CLUSTER_ID_RE.match(cluster):
            errors.append("cluster ID: letters/digits/underscores only")
        elif cluster:
            changes["ark_cluster_id"] = cluster
    if "satisfactory_api_token" in data:
        changes["satisfactory_api_token"] = str(data["satisfactory_api_token"]).strip()
    if "server_name_prefix" in data:
        prefix = str(data["server_name_prefix"]).strip()
        if not _NAME_PREFIX_RE.match(prefix):
            errors.append("server name prefix: up to 30 letters, digits, spaces or _ . - [ ] ( )")
        else:
            changes["server_name_prefix"] = prefix
    if "default_backup_keep" in data:
        try:
            changes["default_backup_keep"] = max(1, min(int(data["default_backup_keep"]), 100))
        except (TypeError, ValueError):
            errors.append("default backups-to-keep must be a number")
    if isinstance(data.get("install_dirs"), dict):
        dirs = dict(current.get("install_dirs", {}))
        for kind in [t.kind for t in games.all_types() if t.install_marker]:
            path = str(data["install_dirs"].get(kind, "")).strip()
            if path and not _PATH_RE.match(path):
                errors.append(f"{kind} install dir: plain path characters only")
            elif path:
                dirs[kind] = path
        changes["install_dirs"] = dirs
    return changes, errors


@app.route("/admin/config", methods=["GET", "POST"])
@login_required
@csrf_required
def admin_config():
    current = config.load()
    if request.method == "POST":
        changes, errors = _settings_changes(request.get_json(silent=True) or {}, current)
        if errors:
            return jsonify({"ok": False, "error": "; ".join(errors)}), 400
        current = config.update(lambda c: c.update(changes))
        audit_log.info("settings changed ip=%s keys=%s", _client_ip(), ",".join(sorted(changes)))
    # report current editable values (admin-only page; token shown for editing)
    timer_on = _command_succeeds(["systemctl", "--user", "is-enabled", "gamedash-backup.timer"])
    return jsonify({
        "ok": True,
        "public_host": current.get("public_host", ""),
        "secrets_conf": current.get("secrets_conf", ""),
        "ark_cluster_id": current.get("ark_cluster_id", ""),
        "server_name_prefix": current.get("server_name_prefix", ""),
        "satisfactory_api_token": current.get("satisfactory_api_token", ""),
        "default_backup_keep": current.get("default_backup_keep", config.DEFAULT_BACKUP_KEEP),
        "install_dirs": current.get("install_dirs", {}),
        "backup_schedule": "Daily at 05:00 local (gamedash-backup.timer)",
        "backup_timer_enabled": timer_on,
    })


@app.route("/admin/passwords", methods=["GET", "POST"])
@login_required
@csrf_required
def admin_passwords():
    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        changes = {}
        for field, key in (("join_password", "GAME_SERVER_PASSWORD"),
                           ("admin_password", "GAME_ADMIN_PASSWORD")):
            val = (data.get(field) or "").strip()
            if not val:
                continue  # blank = keep current
            if not _PW_RE.match(val):
                return jsonify({"ok": False, "error": f"{field.replace('_', ' ')}: use 1-64 chars, "
                                "letters/digits/!@#%^&*()_+-=:.,  (no spaces, quotes, $, ` or \\)."}), 400
            changes[key] = val
        if not changes:
            return jsonify({"ok": False, "error": "Nothing to change — both fields were blank."}), 400
        try:
            registry.write_secrets(changes)
        except Exception as e:
            app_log.exception("password write failed")
            return jsonify({"ok": False, "error": f"could not write secrets file: {e}"}), 500
        # audit WITHOUT values — only which keys changed
        audit_log.info("game passwords changed ip=%s keys=%s", _client_ip(), ",".join(sorted(changes)))
        running = [s.name for s in registry.load_servers() if monitor.unit_active(s.unit)]
        return jsonify({"ok": True, "changed": sorted(changes),
                        "message": "Saved. Restart servers to apply the new password(s).",
                        "restart": running})
    stored = registry.load_secrets()
    return jsonify({"ok": True,
                    "join_set": bool(stored.get("GAME_SERVER_PASSWORD")),
                    "admin_set": bool(stored.get("GAME_ADMIN_PASSWORD")),
                    "secrets_path": config.secrets_path()})


@app.route("/admin/backups/run-all", methods=["POST"])
@login_required
@csrf_required
def admin_backups_run_all():
    threading.Thread(target=backups.backup_all, name="backup-all-manual", daemon=True).start()
    audit_log.info("backup run-all triggered ip=%s", _client_ip())
    return jsonify({"ok": True, "message": "Backing up all servers in the background — refresh in a moment."})


@app.route("/admin/updates/check", methods=["POST"])
@login_required
@csrf_required
def admin_updates_check():
    updates.checker.trigger()
    osupdates.checker.trigger()
    audit_log.info("update check triggered ip=%s", _client_ip())
    return jsonify({"ok": True})


@app.route("/admin/updates/apply", methods=["POST"])
@login_required
@csrf_required
def admin_updates_apply():
    ip = _client_ip()
    data = request.get_json(silent=True) or {}
    app_id = data.get("app", "")
    confirm = bool(data.get("confirm", False))
    try:
        result = controls.start_update(app_id, confirm=confirm)
        audit_log.info("update APPLY started: app=%s ip=%s", app_id, ip)
        return jsonify(result)
    except controls.ActionError as e:
        audit_log.warning("update apply FAILED: app=%s ip=%s err=%s", app_id, ip, e)
        return jsonify({"ok": False, "error": str(e)}), 400


@app.route("/admin/action", methods=["POST"])
@login_required
@csrf_required
def admin_action():
    ip = _client_ip()
    data = request.get_json(silent=True) or {}
    key = data.get("key", "")
    action = data.get("action", "")
    message = data.get("message", "")
    target = data.get("target", "")
    confirm = bool(data.get("confirm", False))
    tgt = f" target={target}" if target else ""
    try:
        result = controls.perform(key, action, message=message, confirm=confirm, target=target)
        audit_log.info("action OK: %s %s%s ip=%s :: %s", action, key, tgt, ip,
                       result.get("message", ""))
        return jsonify(result)
    except controls.ConfirmRequired as c:
        audit_log.info("action needs-confirm: %s %s ip=%s (%s players online)", action, key, ip, c.players)
        return _players_online(c)
    except controls.ActionError as e:
        audit_log.warning("action FAILED: %s %s%s ip=%s err=%s", action, key, tgt, ip, e)
        return jsonify({"ok": False, "error": str(e)}), 400


@app.route("/admin/alerts", methods=["GET", "POST"])
@login_required
@csrf_required
def admin_alerts():
    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        previous = alerts.destinations()
        raw = data.get("destinations")
        if not isinstance(raw, list) or len(raw) > 10:
            return jsonify({"ok": False, "error": "Up to 10 alert destinations."}), 400
        try:   # the browser only knows secret values as a placeholder: keep the stored ones
            dests = [notifiers.clean(d if isinstance(d, dict) else {},
                                     previous[i] if i < len(previous) else None)
                     for i, d in enumerate(raw)]
        except ValueError as e:
            return jsonify({"ok": False, "error": str(e)}), 400
        changed = {"alert_destinations": dests, "alert_channel": "none", "alert_target": ""}
        for k in ("alert_on_recovery", "alert_on_unreachable", "alert_on_disabled"):
            if k in data:
                changed[k] = bool(data[k])
        config.update(lambda c: c.update(changed))
        audit_log.info("alert settings changed ip=%s destinations=%s", _client_ip(),
                       ",".join(d["type"] for d in dests) or "none")
        test = data.get("test")
        results = None
        if test == "all":
            results = alerts.send_test()
        elif isinstance(test, int) and 0 <= test < len(dests):
            results = alerts.send_test(dests[test])
        return jsonify({"ok": True, "test_results": results, **_alert_view()})
    return jsonify(_alert_view())


def _alert_view() -> dict:
    current = config.load()
    return {"services": notifiers.describe(),
            "destinations": [notifiers.public_view(d) for d in alerts.destinations(current)],
            "alert_on_recovery": current.get("alert_on_recovery", True),
            "alert_on_unreachable": current.get("alert_on_unreachable", True),
            "alert_on_disabled": current.get("alert_on_disabled", False)}


@app.route("/admin/portpool", methods=["GET", "POST"])
@login_required
@csrf_required
def admin_portpool():
    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        pool: dict = {}
        errors: list[str] = []
        for k in ports.CLASSES:
            rng = data.get(k)
            if rng in (None, "", [], {}):
                continue  # cleared → that class falls back to template defaults
            try:
                lo, hi = int(rng[0]), int(rng[1])
            except (TypeError, ValueError, IndexError, KeyError):
                errors.append(f"{k}: enter both a low and a high port")
                continue
            if not (1 <= lo <= hi <= 65535):
                errors.append(f"{k}: range must be within 1-65535 with low ≤ high")
                continue
            pool[k] = [lo, hi]
        # ranges must not overlap one another (a port can't be both game and rcon)
        spans = sorted(pool.items(), key=lambda kv: kv[1][0])
        for (ka, a), (kb, b) in zip(spans, spans[1:]):
            if a[1] >= b[0]:
                errors.append(f"{ka} and {kb} ranges overlap")
        if errors:
            return jsonify({"ok": False, "error": "; ".join(errors)}), 400
        config.update(lambda c: c.__setitem__("port_pool", pool))
        audit_log.info("port pool changed ip=%s pool=%s", _client_ip(), pool)
        return jsonify({"ok": True, "port_pool": pool})
    return jsonify({"port_pool": config.load().get("port_pool") or {}})


@app.route("/admin/logs/<key>")
@login_required
def admin_logs(key):
    return jsonify({"ok": True, "text": controls.read_logs(key, request.args.get("lines", 300))})


@app.route("/admin/servers/reach")
@login_required
def admin_servers_reach():
    return jsonify(reach.check(request.args.get("key", "")))


@app.route("/admin/servers/types")
@login_required
def admin_server_types():
    # which game types can currently be provisioned via the dashboard
    types = [{"kind": "custom", "label": "Custom service (advanced)", "custom": True, "extra_fields": []}]
    # Custom stays first; the games follow in alphabetical order.
    for game in sorted(games.all_types(), key=lambda t: t.label.lower()):
        if game.provisionable:
            types.append({"kind": game.kind, "label": game.label, "custom": False,
                          "installed": installs.is_installed(game) if game.install_marker else True,
                          "extra_fields": list(game.extra_fields) + game.port_fields(),
                          "needs_clone": game.needs_install_clone,
                          "note": game.provision_note,
                          "eula": game.eula,
                          "hint": game.provision_hint,
                          "mod_profiles": game.mod_profiles})
    return jsonify({"types": types})


@app.route("/admin/cert", methods=["GET", "POST"])
@login_required
@csrf_required
def admin_cert():
    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        return jsonify(certs.start(data.get("domain", ""), data.get("email", ""),
                                   bool(data.get("agree")), dashboard_port=_dashboard_port()))
    return jsonify({"ok": True, "cert": certs.info(), "job": certs.status_job(),
                    "lan_ip": reach.lan_ip(), "suggest": config.load().get("public_host", ""),
                    "terms_url": certs.TERMS_URL, "available": bool(certs.certbot_path())})


@app.route("/admin/games")
@login_required
def admin_games():
    return jsonify({"ok": True, "games": installs.catalog(), "job": installs.status(),
                    "steam_terms": installs.steam_terms_url()})


@app.route("/admin/games/install", methods=["POST"])
@login_required
@csrf_required
def admin_games_install():
    kind = (request.get_json(silent=True) or {}).get("kind", "")
    return jsonify(installs.start(kind))


@app.route("/admin/games/uninstall", methods=["POST"])
@login_required
@csrf_required
def admin_games_uninstall():
    kind = (request.get_json(silent=True) or {}).get("kind", "")
    return jsonify(installs.uninstall(kind))


@app.route("/admin/servers/script", methods=["GET", "POST"])
@login_required
@csrf_required
def admin_servers_script():
    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        return jsonify(provision.write_script(data.get("key", ""), data.get("content", "")))
    return jsonify(provision.read_script(request.args.get("key", "")))


@app.route("/admin/servers/add", methods=["POST"])
@login_required
@csrf_required
def admin_servers_add():
    spec = request.get_json(silent=True) or {}
    try:
        result = provision.create(spec)
        game = games.get(str(spec.get("kind", "")))
        eula = game.eula if game is not None else None
        if eula and eula.get("required"):     # a record of who agreed to what, and when
            audit_log.info("EULA accepted: game=%s server=%s terms=%s ip=%s", game.kind,
                           str(spec.get("key", ""))[:31], eula["url"], _client_ip())
        return jsonify(result)
    except provision.ProvisionConfirm as c:
        return jsonify({"ok": False, "confirm_required": True, "provision": {
            "needed_gb": round(c.needed / 2**30, 1),
            "free_gb": round(c.free / 2**30, 1),
            "ram_avail_gb": round(c.ram_avail / 2**30, 1),
            "dst": c.dst,
        }}), 409


@app.route("/admin/servers/remove", methods=["POST"])
@login_required
@csrf_required
def admin_servers_remove():
    key = (request.get_json(silent=True) or {}).get("key", "")
    return jsonify(provision.destroy(key))


@app.route("/admin/servers/backups", methods=["GET", "POST"])
@login_required
@csrf_required
def admin_backups():
    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        return jsonify(backups.create_backup(data.get("key", ""), label=data.get("label", "")))
    key = request.args.get("key", "")
    s = registry.by_key().get(key)
    if not s:
        return jsonify({"ok": False, "error": "unknown server"}), 400
    saves = backups.save_paths(s)
    return jsonify({"ok": True, "backups": backups.list_backups(key),
                    "keep": s.backup_keep, "kind": s.kind,
                    "save_paths": [p["path"] for p in saves],
                    "has_cluster": any(p.get("role") == "cluster" for p in saves),
                    "can_backup": bool(saves), "online": monitor.unit_active(s.unit)})


@app.route("/admin/servers/backups/delete", methods=["POST"])
@login_required
@csrf_required
def admin_backups_delete():
    data = request.get_json(silent=True) or {}
    return jsonify(backups.delete_backup(data.get("key", ""), data.get("name", "")))


@app.route("/admin/servers/backupkeep", methods=["POST"])
@login_required
@csrf_required
def admin_backups_keep():
    data = request.get_json(silent=True) or {}
    return jsonify(backups.set_keep(data.get("key", ""),
                                    data.get("keep", config.DEFAULT_BACKUP_KEEP)))


@app.route("/admin/servers/restore", methods=["POST"])
@login_required
@csrf_required
def admin_restore():
    ip = _client_ip()
    data = request.get_json(silent=True) or {}
    key, name = data.get("key", ""), data.get("name", "")
    include_cluster = bool(data.get("include_cluster", True))
    try:
        result = backups.restore_backup(key, name, confirm=bool(data.get("confirm")),
                                        include_cluster=include_cluster)
        audit_log.info("backup RESTORE ok: %s %s ip=%s", key, name, ip)
        return jsonify(result)
    except controls.ActionError as e:
        audit_log.warning("backup RESTORE failed: %s %s ip=%s err=%s", key, name, ip, e)
        raise


@app.route("/admin/servers/backup-download")
@login_required
def admin_backup_download():
    path = backups.backup_file(request.args.get("key", ""), request.args.get("name", ""))
    return send_file(path, as_attachment=True, download_name=request.args.get("name", "backup.tar.gz"))


# ---- errors ----------------------------------------------------------------
# Routes just call into the modules; these turn their exceptions into the replies
# the page expects.

def _players_online(c: controls.ConfirmRequired):
    """409: players are on — the page asks the owner, then resends with confirm."""
    return jsonify({"ok": False, "confirm_required": True,
                    "players": c.players, "names": c.names}), 409


@app.errorhandler(controls.ConfirmRequired)
def _handle_confirm(c):
    return _players_online(c)


@app.errorhandler(controls.ActionError)
def _handle_action_error(e):
    """A refused or failed action: the message is already written for the owner."""
    return jsonify({"ok": False, "error": str(e)}), 400


@app.errorhandler(Exception)
def _handle_error(e):
    if isinstance(e, HTTPException):
        return e  # let normal 4xx/redirects pass through
    app_log.exception("unhandled error on %s %s", request.method, request.path)
    return jsonify({"ok": False, "error": "internal error"}), 500


def main():
    app.run(host=cfg["bind_host"], port=cfg["bind_port"], threaded=True)


# Start the poller + update checkers on import so they run under any WSGI server.
poller.start()
updates.checker.start()
osupdates.checker.start()

if __name__ == "__main__":
    main()
