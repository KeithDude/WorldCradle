"""provision.py — create/remove realmcradle-managed servers.

Generates a `systemctl --user` unit (~/.config/systemd/user/realmcradle-<key>.service)
and a servers.json entry, allocating free ports. Only servers with
managed=="realmcradle" can be torn down here — legacy (hand-made) servers are
refused, so the existing fleet can't be deleted by accident.

Most games provision synchronously (write a small launch script into a shared
install). Games that can't share an install (`needs_install_clone`: Palworld,
Barotrauma, Eco and others) clone the base install first — a multi-GB copy — so they run as a
background job, gated behind a disk pre-flight + explicit confirm.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import threading

import config
import games
import jobs
import registry
import store
import systemd
from applog import app_log, audit_log
from games.base import ActionError

SYSTEMD_DIR = os.path.expanduser("~/.config/systemd/user")
KEY_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,30}$")
# Never handed out as game ports: SSH, DNS, web (80/443), the dashboard (8443), the dashboard's
# development server (8770, config "bind_port") and 8888, a common local web/admin port.
RESERVED = {22, 53, 80, 443, 8443, 8770, 8888}


class ProvisionConfirm(Exception):
    """A clone-install provision needs the operator to confirm the disk cost."""
    def __init__(self, needed: int, free: int, ram_avail: int, dst: str):
        self.needed = needed
        self.free = free
        self.ram_avail = ram_avail
        self.dst = dst
        super().__init__("confirmation required")


def _unit_name(key: str) -> str:
    return f"realmcradle-{key}.service"


def _unit_path(key: str) -> str:
    return os.path.join(SYSTEMD_DIR, _unit_name(key))


def used_ports() -> set[int]:
    """Ports already taken — by configured servers and by anything listening."""
    used: set[int] = set(RESERVED)
    for s in registry.load_servers():
        used |= s.all_ports()
    try:
        out = subprocess.run(["ss", "-ltnuH"], capture_output=True, text=True, timeout=5).stdout
        for m in re.finditer(r"[:.](\d+)\s", out):
            used.add(int(m.group(1)))
    except Exception:
        pass
    return used


def _port_plan(requests: list[tuple]) -> set[int]:
    """The taken-port set to allocate against, with the ports the operator typed released from it.

    `requests` = [(label, typed value, span)] for the boxes the operator filled in. Any port may be
    typed — even one another server uses, so servers can take turns on one set of router ports;
    Start refuses while the ports are in use (controls.port_clash). Only the reserved ports
    (the dashboard's own, SSH, …) stay refused. Blank boxes are allocated from free ports."""
    used = used_ports()
    for _label, raw, span in requests:
        try:
            first = int(str(raw).strip())
        except (TypeError, ValueError):
            continue  # not a number — ports.claim reports it properly
        for q in range(first, first + span):
            if q not in RESERVED:
                used.discard(q)
    return used


def _custom_fields(spec: dict, use_pool: bool) -> tuple[str, dict]:
    name = (spec.get("name") or "").strip()
    exec_start = (spec.get("exec_start") or "").strip()
    if not name or not exec_start:
        raise ActionError("Name and launch command are required.")
    wd = os.path.expanduser((spec.get("working_dir") or "~").strip())
    if not os.path.isdir(wd):
        raise ActionError(f"Working directory does not exist: {wd}")
    if use_pool:
        # operator opted into the pool → allocate instead of using the textbox
        import ports
        u = used_ports()
        gp = ports.alloc("game", 7100, u, use_pool=True)
        qp = ports.alloc("query", 27030, u, use_pool=True) if spec.get("query_port") else None
    else:
        import ports
        if not str(spec.get("game_port") or "").strip():
            raise ActionError("A valid game port is required.")
        requests = [("Game port", spec.get("game_port"), 1)]
        if spec.get("query_port"):
            requests.append(("Query port", spec.get("query_port"), 1))
        u = _port_plan(requests)
        gp = ports.claim(spec.get("game_port"), u, 1, "Game port")
        qp = ports.claim(spec.get("query_port"), u, 1, "Query port") if spec.get("query_port") else None
    # optional save folder so backups know what to archive for this custom service
    save_root = os.path.expanduser((spec.get("save_root") or "").strip())
    if save_root and not os.path.isdir(save_root):
        raise ActionError(f"Save folder does not exist: {save_root}")
    fields = {
        "exec_start": exec_start, "working_dir": wd, "game_port": gp,
        "query_port": qp, "rcon_port": None, "a2s": bool(qp),
        "proc_match": (spec.get("proc_match") or "").strip(),
        "server_name": (spec.get("server_name") or name).strip(),
        "join_port": gp, "install_dir": wd, "steam_app": spec.get("steam_app"),
        "save_root": save_root,
    }
    return name, fields


def _wanted_ports(spec: dict) -> dict:
    """Ports the operator typed on the Add form: {"game": "7790", ...}. Blank
    boxes are left out, so those ports are allocated automatically."""
    return {k[5:]: v for k, v in spec.items()
            if k.startswith("port_") and v is not None and str(v).strip() != ""}


def _port_requests(game, spec: dict) -> list[tuple]:
    """(label, typed value, span) for each of the game's ports the operator filled in."""
    wanted = _wanted_ports(spec)
    return [(p["label"], wanted[p["name"]], p.get("span", 1))
            for p in game.port_layout if p["name"] in wanted]


def _template_fields(kind: str, spec: dict, use_pool: bool) -> tuple[str, dict]:
    game = games.get(kind)
    if not game or not getattr(game, "provisionable", False):
        raise ActionError(f"Auto-provisioning isn't available for '{kind}' yet — use Custom service.")
    used = _port_plan(_port_requests(game, spec))
    ports = game.provision_ports(used, use_pool, _wanted_ports(spec))
    fields = game.provision(spec, ports)  # writes config/launch files
    fields["port_map"] = dict(ports)
    display = (spec.get("name") or fields.get("server_name") or "").strip()
    return f"{game.label} · {display}", fields


def _unit_text(name: str, fields: dict) -> str:
    svc = [
        "[Unit]",
        f"Description=realmcradle: {name}",
        "After=network-online.target", "Wants=network-online.target", "",
        "[Service]", "Type=simple",
        f"WorkingDirectory={fields['working_dir']}",
        f"ExecStart={fields['exec_start']}",
    ]
    if fields.get("exec_stop"):       # graceful shutdown (e.g. ARK RCON DoExit)
        svc.append(f"ExecStop={fields['exec_stop']}")
    if fields.get("kill_signal"):     # e.g. Valheim/Satisfactory SIGINT for a clean save
        svc.append(f"KillSignal={fields['kill_signal']}")
    if fields.get("timeout_stop"):
        svc.append(f"TimeoutStopSec={fields['timeout_stop']}")
    # A server that exits because it was told to stop (Ctrl-C / SIGTERM, or the exit codes for
    # those) stopped normally: not a failure to restart or to count as a crash.
    svc.append("SuccessExitStatus=130 143 SIGINT SIGTERM")
    svc += ["Restart=on-failure", "RestartSec=10", "", "[Install]", "WantedBy=default.target", ""]
    return "\n".join(svc)


def _store_entry(key: str, kind: str, name: str, fields: dict) -> dict:
    entry = {
        "key": key, "kind": kind, "name": name,
        "unit": _unit_name(key), "managed": "realmcradle",
        "game_port": fields["game_port"], "query_port": fields.get("query_port"),
        "rcon_port": fields.get("rcon_port"), "a2s": bool(fields.get("a2s")),
        "proc_match": fields.get("proc_match", ""),
        "server_name": fields.get("server_name", name),
        "join_port": fields.get("join_port", fields["game_port"]),
        "install_dir": fields.get("install_dir", ""),
        "steam_app": fields.get("steam_app"),
    }
    if fields.get("log_path"):
        entry["log_path"] = fields["log_path"]
    if fields.get("rcon_password_ref"):
        entry["rcon_password_ref"] = fields["rcon_password_ref"]
    # save-location metadata (drives backup/restore via GameType.save_paths)
    for k in ("save_dir", "save_root", "world", "cluster_id", "extra_ports", "port_map"):
        if fields.get(k):
            entry[k] = fields[k]
    entry["backup_keep"] = int(fields.get("backup_keep")
                               or config.load().get("default_backup_keep") or 5)
    return entry


def _register(key: str, kind: str, name: str, fields: dict, start: bool) -> str:
    """Write the unit, reload systemd, record the store entry, optionally start.
    Returns a note to append to the success message ("" normally)."""
    os.makedirs(SYSTEMD_DIR, exist_ok=True)
    with open(_unit_path(key), "w", encoding="utf-8") as f:
        f.write(_unit_text(name, fields))
    systemd.check("daemon-reload")
    store.add(_store_entry(key, kind, name, fields))
    audit_log.info("server CREATED key=%s kind=%s name=%r unit=%s", key, kind, name, _unit_name(key))
    if not start:
        return ""
    import controls
    clash = controls.port_clash(registry.by_key()[key])
    if clash:   # creating it is fine; starting it has to wait until its ports are free
        return f" Not started: its ports are in use — {clash}"
    systemd.check("enable", "--now", _unit_name(key), timeout=130)
    return ""


def adopt(key: str, spec: dict, ports: dict) -> dict:
    """Bring an existing server onto its game's current standard launch: new launch and stop
    scripts, service file and record, made the way a new server's are, from `spec` (its
    settings, as the Add form would give them) and `ports` (its ports by name). Its settings
    files, world and saves are not touched. Everything replaced is kept beside it with a
    ".before-adopt-<time>" suffix. Doesn't start or stop it — the caller does that, with the
    server stopped."""
    import time
    entry = store.get(key)
    if entry is None:
        raise ActionError(f"No server with key '{key}'.")
    game = games.get(entry["kind"])
    if game is None or not hasattr(game, "command"):
        raise ActionError(f"{entry['kind']} servers can't be adopted.")
    if systemd.is_active(_unit_name(key)):
        raise ActionError(f"Stop {entry['name']} first.")
    install = os.path.expanduser(entry.get("install_dir") or config.install_dir(entry["kind"]))
    stamp = time.strftime("%Y%m%d-%H%M%S")
    kept = []
    for path in (_unit_path(key), os.path.join(install, f"realmcradle-{key}-run.sh"),
                 os.path.join(install, f"realmcradle-{key}-stop.sh"), store.STORE_PATH):
        if os.path.isfile(path):
            shutil.copy2(path, f"{path}.before-adopt-{stamp}")
            kept.append(path)
    full = {**spec, "key": key, "kind": entry["kind"], "install_dir": install, "adopt": True}
    full.setdefault("name", entry.get("server_name") or entry["name"])
    fields = game.provision(full, ports)
    old_stop = os.path.join(install, f"realmcradle-{key}-stop.sh")
    if not fields.get("exec_stop") and os.path.isfile(old_stop):
        os.unlink(old_stop)          # the old stop script no longer applies (a copy is kept)
    with open(_unit_path(key), "w", encoding="utf-8") as f:
        f.write(_unit_text(entry["name"], fields))
    systemd.check("daemon-reload")
    new = _store_entry(key, entry["kind"], entry["name"], fields)
    for k in ("backup_keep", "notes"):      # the owner's own choices carry over
        if k in entry:
            new[k] = entry[k]
    store.replace(key, new)
    audit_log.info("server ADOPTED key=%s kind=%s (kept: %s)", key, entry["kind"], ", ".join(kept))
    return {"ok": True, "message": f"{entry['name']} now uses the standard {game.label} launch.",
            "kept": [f"{p}.before-adopt-{stamp}" for p in kept], "entry": new}


def create(spec: dict) -> dict:
    """Create a realmcradle-managed server: custom (kind='custom', caller gives the
    launch command) or a game template (kind in games, auto config+ports).
    Games that need their own copy of the install go through the background job."""
    key = (spec.get("key") or "").strip().lower()
    if not KEY_RE.match(key):
        raise ActionError("Key must be lowercase letters/digits/dashes (2-31 chars).")
    if store.get(key) or registry.by_key().get(key):
        raise ActionError(f"A server with key '{key}' already exists.")
    kind = spec.get("kind", "custom")
    use_pool = bool(spec.get("use_pool"))

    game = games.get(kind) if kind != "custom" else None
    eula = game.eula if game is not None else None
    if eula and eula.get("required") and spec.get("eula") is not True:
        raise ActionError(f"Please read the {eula['name']} ({eula['url']}) and tick the box to agree — "
                          f"it is required before a {game.label} server may be created.")
    if game is not None and getattr(game, "needs_install_clone", False):
        return _create_cloned(spec, key, game, use_pool)

    name, fields = (_custom_fields(spec, use_pool) if kind == "custom"
                    else _template_fields(kind, spec, use_pool))
    note = _register(key, kind, name, fields, bool(spec.get("start")))
    return {"ok": True, "message": f"Added '{name}'.{note}"}


# ---- clone-install provisioning (async) ------------------------------------
provision_job = jobs.Job("provision")


def provision_status() -> dict:
    return provision_job.status()


def _gb(n: int) -> str:
    """A size in binary GB for a message: "0.4 GB", "12 GB"."""
    gb = n / 2**30
    return f"{gb:.1f} GB" if gb < 10 else f"{gb:.0f} GB"


def _dir_size(path: str) -> int:
    try:
        out = subprocess.run(["du", "-sb", path], capture_output=True, text=True, timeout=60).stdout
        return int(out.split(None, 1)[0])
    except Exception:
        total = 0
        for root, _dirs, files in os.walk(path):
            for fn in files:
                try:
                    total += os.path.getsize(os.path.join(root, fn))
                except OSError:
                    pass
        return total


def _ram_available() -> int:
    try:
        for line in open("/proc/meminfo"):
            if line.startswith("MemAvailable:"):
                return int(line.split()[1]) * 1024
    except OSError:
        pass
    return 0


def _create_cloned(spec: dict, key: str, game, use_pool: bool) -> dict:
    src = config.install_dir(game.kind)
    if not os.path.isdir(src):
        raise ActionError(f"{game.label} isn't installed ({src} missing).")
    dst = f"{src.rstrip('/')}-{key}"
    if os.path.exists(dst):
        raise ActionError(f"Target install dir already exists: {dst}")
    busy = "Another server is already being provisioned — wait for it to finish."
    if provision_job.running:
        raise ActionError(busy)

    used = _port_plan(_port_requests(game, spec))
    needed = _dir_size(src)
    free = shutil.disk_usage(os.path.dirname(dst)).free
    if not spec.get("confirm"):
        raise ProvisionConfirm(needed, free, _ram_available(), dst)
    if needed > free:
        raise ActionError(f"Not enough disk: need about {_gb(needed)}, only {_gb(free)} free.")

    # Allocate ports up front so a clash fails fast (before the long copy).
    ports = game.provision_ports(used, use_pool, _wanted_ports(spec))
    provision_job.begin(busy, key=key, kind=game.kind, step="preparing")
    threading.Thread(target=_run_clone_job, name=f"provision-{key}",
                     args=(spec, key, game, src, dst, ports),
                     daemon=True).start()
    return {"ok": True, "message": f"Provisioning '{spec.get('name') or key}' — "
            f"copying a {_gb(needed)} install in the background. "
            f"It'll appear when ready."}


def _run_clone_job(spec, key, game, src, dst, ports):
    try:
        provision_job.step("cloning install (copying files)")
        # cp -a: preserve perms/symlinks/timestamps. Copy into a temp then rename
        # so a crash can't leave a half-populated dst that looks complete.
        tmp = dst + ".partial"
        if os.path.exists(tmp):
            shutil.rmtree(tmp, ignore_errors=True)
        r = subprocess.run(["cp", "-a", src, tmp], capture_output=True, text=True, timeout=3600)
        if r.returncode != 0:
            raise ActionError(f"clone failed: {(r.stderr or r.stdout).strip()[:200]}")
        for sub in game.clone_clear_dirs:   # start with a fresh world, not a copied one
            shutil.rmtree(os.path.join(tmp, sub), ignore_errors=True)
        os.replace(tmp, dst)

        provision_job.step("configuring")
        spec = dict(spec)
        spec["install_dir"] = dst
        fields = game.provision(spec, ports)
        fields["port_map"] = dict(ports)
        display = (spec.get("name") or fields.get("server_name") or key).strip()
        name = f"{game.label} · {display}"
        note = _register(key, game.kind, name, fields, bool(spec.get("start")))

        provision_job.finish(True, f"Added '{name}'.{note}", name=name)
        app_log.info("provision %s: done", key)
    except Exception as e:
        app_log.exception("provision %s crashed", key)
        shutil.rmtree(dst + ".partial", ignore_errors=True)
        provision_job.finish(False, str(e))


# ---- launch-script editor --------------------------------------------------
_MAX_SCRIPT = 64 * 1024  # generous ceiling for a launch script
_MAX_LINES = 500
_MAX_LINE = 4000
# Allowed shebangs — a launch script is a shell script, nothing else.
_SHEBANG_RE = re.compile(r"^#!\s*(/bin/sh|/bin/bash|/usr/bin/sh|/usr/bin/bash|/usr/bin/env\s+(sh|bash))\b")
# High-signal patterns that have no business in a game launch script. This is
# defense-in-depth (the editor is already admin-only + CSRF + path-locked); it
# blocks an edit from being turned into a reverse shell / persistence / wipe.
# Tuned to NOT trip the legitimate generated scripts (which use curl, python
# heredocs, pipes to grep, sourcing secrets, exec of the game binary).
_DANGER = [
    (re.compile(r"/dev/(tcp|udp)/"), "raw network socket (reverse shell)"),
    (re.compile(r"\b(nc|ncat|netcat)\b[^\n]*\s-[a-z]*e"), "netcat command execution"),
    (re.compile(r"\b(bash|sh|zsh)\b\s+-[a-z]*i\b"), "interactive shell"),
    (re.compile(r"\bmkfifo\b"), "named pipe (reverse shell)"),
    (re.compile(r"(curl|wget|fetch)\b[^\n|]*\|\s*(sudo\s+)?(sh|bash|zsh|python|perl|ruby)\b", re.I), "pipe download to interpreter"),
    (re.compile(r"\b(base64|xxd|openssl)\b[^\n|]*\|\s*(sh|bash)\b", re.I), "decode-and-execute"),
    (re.compile(r"\beval\b[^\n]*\$\(\s*(curl|wget)", re.I), "eval of downloaded content"),
    (re.compile(r":\s*\(\s*\)\s*\{\s*:?\s*\|"), "fork bomb"),
    (re.compile(r"\bsudo\b"), "sudo (privilege escalation)"),
    (re.compile(r"\bchpasswd\b|\bpasswd\b\s"), "password change"),
    (re.compile(r"\.ssh/|authorized_keys|id_rsa|id_ed25519"), "SSH key tampering"),
    (re.compile(r"\bcrontab\b|/etc/cron|\bsystemd-run\b"), "scheduled-task persistence"),
    (re.compile(r">>?\s*(/etc/|~?/\.bashrc|~?/\.bash_profile|~?/\.profile|/etc/sudoers)"), "writing to system/profile files"),
    (re.compile(r"\bmkfs\b|\bdd\b[^\n]*\bof=/dev/"), "disk wipe"),
    (re.compile(r"\brm\s+-[a-z]*[rf][a-z]*\s+(/|~|\$HOME|\*|\$\{?HOME)"), "recursive delete of home/root"),
    (re.compile(r"\bchmod\b\s+-?R?\s*0?777\s+/"), "world-writable system path"),
]


def _validate_script(content: str) -> None:
    """Reject a launch script that is malformed or contains content that doesn't
    belong in a game launcher. Raises ActionError naming the problem."""
    if not isinstance(content, str) or not content.strip():
        raise ActionError("Script is empty.")
    if len(content) > _MAX_SCRIPT:
        raise ActionError("Script is too large.")
    # no NUL or other control chars (tab/newline/carriage-return are fine)
    if any((ord(c) < 32 and c not in "\t\n\r") or ord(c) == 127 for c in content):
        raise ActionError("Script contains control characters — not allowed.")
    if not _SHEBANG_RE.match(content):
        raise ActionError("Script must start with a shell shebang (#!/bin/sh or #!/bin/bash).")
    lines = content.splitlines()
    if len(lines) > _MAX_LINES:
        raise ActionError(f"Script has too many lines (>{_MAX_LINES}).")
    for n, line in enumerate(lines, 1):
        if len(line) > _MAX_LINE:
            raise ActionError(f"Line {n} is too long.")
        for rx, why in _DANGER:
            if rx.search(line):
                raise ActionError(f"Rejected: line {n} looks dangerous ({why}). "
                                  f"Launch scripts may not contain this.")


def _script_path(key: str) -> str:
    """Path of a realmcradle-managed server's generated run script, validated.

    Only a managed server whose unit's ExecStart points at its own
    `realmcradle-<key>-run.sh` is editable — this excludes legacy servers and
    custom services (whose ExecStart is an arbitrary command, not our script).
    """
    e = store.get(key)
    if not e:
        raise ActionError(f"No realmcradle-managed server with key '{key}'.")
    if e.get("managed") != "realmcradle":
        raise ActionError("Only realmcradle-managed servers have an editable launch script.")
    unit = _unit_path(key)
    if not os.path.exists(unit):
        raise ActionError("Unit file not found.")
    exec_start = ""
    for line in open(unit, encoding="utf-8"):
        if line.startswith("ExecStart="):
            exec_start = line[len("ExecStart="):].strip()
            break
    token = exec_start.split()[0].strip('"') if exec_start else ""
    if (not token or not os.path.isabs(token)
            or os.path.basename(token) != f"realmcradle-{key}-run.sh"
            or not os.path.isfile(token)):
        raise ActionError("This server has no editable realmcradle launch script "
                          "(custom services run a command you set directly).")
    return os.path.realpath(token)


def read_script(key: str) -> dict:
    path = _script_path(key)
    with open(path, encoding="utf-8") as f:
        return {"ok": True, "path": path, "content": f.read()}


def write_script(key: str, content: str) -> dict:
    path = _script_path(key)
    # normalise line endings, then validate hard before touching disk
    content = (content or "").replace("\r\n", "\n").replace("\r", "\n")
    try:
        _validate_script(content)
    except ActionError as e:
        audit_log.warning("server SCRIPT rejected key=%s reason=%s", key, e)
        raise
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(content)
    os.chmod(tmp, 0o755)
    os.replace(tmp, path)
    audit_log.info("server SCRIPT edited key=%s path=%s", key, path)
    return {"ok": True, "message": "Launch script saved — takes effect on next start/restart."}


def destroy(key: str) -> dict:
    e = store.get(key)
    if not e:
        raise ActionError(f"No realmcradle-managed server with key '{key}'.")
    if e.get("managed") != "realmcradle":
        raise ActionError("Refusing to remove a legacy (hand-made) server.")
    unit = e.get("unit", _unit_name(key))
    try:
        systemd.check("disable", "--now", unit, timeout=130)
    except ActionError:
        pass  # may already be stopped/disabled
    path = _unit_path(key)
    if os.path.exists(path):
        os.remove(path)
    systemd.check("daemon-reload")
    store.remove(key)
    # A Windows-only server's private Wine environment (~1 GB) holds no saves — remove it too.
    extra = ""
    from games import common
    prefix = common.wine_prefix(e.get("kind", ""), key)
    if e.get("kind") and os.path.basename(prefix).startswith(".wine-rc-") and os.path.isdir(prefix):
        shutil.rmtree(prefix, ignore_errors=True)
        extra = " Its Wine environment was deleted."
    audit_log.info("server REMOVED key=%s unit=%s%s", key, unit, " (wine prefix deleted)" if extra else "")
    return {"ok": True, "message": f"Removed '{e.get('name', key)}'.{extra} (Save data, if any, left on disk.)"}
