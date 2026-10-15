"""provision.py — create/remove gamedash-managed servers.

Generates a `systemctl --user` unit (~/.config/systemd/user/gamedash-<key>.service)
and a servers.json entry, allocating free ports. Only servers with
managed=="gamedash" can be torn down here — legacy (hand-made) servers are
refused, so the existing fleet can't be deleted by accident.

Most games provision synchronously (write a small launch script into a shared
install). Games that can't share an install (`needs_install_clone`, e.g.
Palworld) clone the base install first — a multi-GB copy — so they run as a
background job, gated behind a disk pre-flight + explicit confirm.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import threading
import time

import config
import games
import registry
import store
from applog import app_log, audit_log
from games.base import ActionError

SYSTEMD_DIR = os.path.expanduser("~/.config/systemd/user")
KEY_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,30}$")
# never hand these out as game ports
RESERVED = {22, 53, 80, 443, 8443, 8770, 8888}


class ProvisionConfirm(Exception):
    """A clone-install provision needs the operator to confirm the disk cost."""
    def __init__(self, needed: int, free: int, ram_avail: int, dst: str):
        self.needed = needed
        self.free = free
        self.ram_avail = ram_avail
        self.dst = dst
        super().__init__("confirmation required")


class PortShareConfirm(Exception):
    """The operator typed a port that another configured server already uses.
    That is allowed (two servers can take turns on one set of forwarded ports)
    but only on purpose — carries what clashes so the UI can explain it.
    `conflicts` = [{"port": int, "label": str, "servers": [display names]}]."""
    def __init__(self, conflicts: list[dict]):
        self.conflicts = conflicts
        super().__init__("port sharing needs confirmation")


def _unit_name(key: str) -> str:
    return f"gamedash-{key}.service"


def _unit_path(key: str) -> str:
    return os.path.join(SYSTEMD_DIR, _unit_name(key))


def _systemctl(*args: str, timeout: int = 60) -> None:
    r = subprocess.run(["systemctl", "--user", *args],
                       capture_output=True, text=True, timeout=timeout)
    if r.returncode != 0:
        raise ActionError(f"systemctl {' '.join(args)} failed: "
                          f"{(r.stderr or r.stdout).strip() or r.returncode}")


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


def port_owners() -> dict[int, list]:
    """port -> the configured servers set up to use it (game/query/rcon, plus
    ARK's raw socket on game port + 1)."""
    owners: dict[int, list] = {}
    for s in registry.load_servers():
        for p in s.all_ports():
            owners.setdefault(p, []).append(s)
    return owners


def _port_plan(spec: dict, requests: list[tuple]) -> tuple[set[int], list]:
    """Work out what the typed ports collide with before anything is created.

    `requests` = [(label, typed value, span)] for the boxes the operator filled
    in. Returns (used, siblings): the taken-port set to allocate against, and
    the servers the new one will share ports with.

    A typed port that belongs to another configured server is a *shareable*
    clash: it raises PortShareConfirm until the request carries share_ports,
    after which those ports are released from `used` so they can be claimed.
    A port held by anything else (another program, a reserved port) stays in
    `used` and is refused as before."""
    used, owners = used_ports(), port_owners()
    conflicts, siblings = [], {}
    for label, raw, span in requests:
        try:
            first = int(str(raw).strip())
        except (TypeError, ValueError):
            continue  # not a number — ports.claim reports it properly
        for q in range(first, first + span):
            if q in owners:
                conflicts.append({"port": q, "label": label,
                                  "servers": [s.name for s in owners[q]]})
                for s in owners[q]:
                    siblings[s.key] = s
    if conflicts and not spec.get("share_ports"):
        raise PortShareConfirm(conflicts)
    for c in conflicts:
        used.discard(c["port"])
    return used, list(siblings.values())


def _join_slot_group(key: str, siblings: list) -> None:
    """Put the new server and everything it shares ports with into one slot
    group, so the dashboard starts only one of them at a time. Reuses a group a
    sibling is already in; members of any other sibling group are folded in."""
    if not siblings:
        return
    groups = [s.slot_group for s in siblings if s.slot_group]
    group = groups[0] if groups else f"port-{min(int(s.game_port) for s in siblings)}"
    members = {s.key for s in siblings} | {key}
    for e in store.load():   # fold in the rest of any group a sibling belonged to
        if e.get("slot_group") and e["slot_group"] in groups:
            members.add(e["key"])
    for k in members:
        store.update(k, slot_group=group)
    audit_log.info("server PORT-SHARE key=%s group=%s members=%s", key, group, ",".join(sorted(members)))


def _running(siblings: list) -> list:
    import monitor
    return [s for s in siblings if monitor.unit_active(s.unit)]


def free_port(start: int, used: set[int]) -> int:
    p = start
    while p in used:
        p += 1
    used.add(p)
    return p


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
        siblings = []
        gp = ports.alloc("game", 7100, u, use_pool=True)
        qp = ports.alloc("query", 27030, u, use_pool=True) if spec.get("query_port") else None
    else:
        import ports
        if not str(spec.get("game_port") or "").strip():
            raise ActionError("A valid game port is required.")
        requests = [("Game port", spec.get("game_port"), 1)]
        if spec.get("query_port"):
            requests.append(("Query port", spec.get("query_port"), 1))
        u, siblings = _port_plan(spec, requests)
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
        "_siblings": siblings if not use_pool else [],
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
    used, siblings = _port_plan(spec, _port_requests(game, spec))
    ports = game.provision_ports(used, use_pool, _wanted_ports(spec))
    fields = game.provision(spec, ports)  # writes config/launch files
    fields["_siblings"] = siblings
    fields["port_map"] = dict(ports)
    display = (spec.get("name") or fields.get("server_name") or "").strip()
    return f"{game.label} · {display}", fields


def _unit_text(name: str, fields: dict) -> str:
    svc = [
        "[Unit]",
        f"Description=gamedash: {name}",
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
    svc += ["Restart=on-failure", "RestartSec=10", "", "[Install]", "WantedBy=default.target", ""]
    return "\n".join(svc)


def _store_entry(key: str, kind: str, name: str, fields: dict) -> dict:
    entry = {
        "key": key, "kind": kind, "name": name,
        "unit": _unit_name(key), "managed": "gamedash",
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
    _systemctl("daemon-reload")
    store.add(_store_entry(key, kind, name, fields))
    audit_log.info("server CREATED key=%s kind=%s name=%r unit=%s", key, kind, name, _unit_name(key))
    siblings = fields.get("_siblings") or []
    _join_slot_group(key, siblings)
    busy = _running(siblings)
    if start and busy:
        # its ports are in use right now — creating it is fine, starting it isn't
        return (f" Not started: {busy[0].name} is running on the shared ports. "
                f"Stop it first, then start this one.")
    if start:
        _systemctl("enable", "--now", _unit_name(key), timeout=130)
    return ""


def create(spec: dict) -> dict:
    """Create a gamedash-managed server: custom (kind='custom', caller gives the
    launch command) or a game template (kind in games, auto config+ports).
    Clone-install games (Palworld) go through the async job path."""
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
_job_lock = threading.Lock()
_provision_job: dict = {"state": "idle"}  # state: idle|running|done|failed


def provision_status() -> dict:
    with _job_lock:
        return dict(_provision_job)


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
    with _job_lock:
        if _provision_job.get("state") == "running":
            raise ActionError("Another server is already being provisioned — wait for it to finish.")

    # Port sharing is confirmed first: it can change which ports the operator
    # wants, and there is no point pricing a multi-GB copy before that is settled.
    used, siblings = _port_plan(spec, _port_requests(game, spec))
    needed = _dir_size(src)
    free = shutil.disk_usage(os.path.dirname(dst)).free
    if not spec.get("confirm"):
        raise ProvisionConfirm(needed, free, _ram_available(), dst)
    if needed > free:
        raise ActionError(f"Not enough disk: need ~{needed // 2**30} GB, only "
                          f"{free // 2**30} GB free.")

    # Allocate ports up front so a clash fails fast (before the long copy).
    ports = game.provision_ports(used, use_pool, _wanted_ports(spec))
    with _job_lock:
        _provision_job.clear()
        _provision_job.update({"state": "running", "key": key, "kind": game.kind,
                               "step": "preparing", "started_ts": time.time()})
    threading.Thread(target=_run_clone_job, name=f"provision-{key}",
                     args=(spec, key, game, src, dst, ports, siblings),
                     daemon=True).start()
    return {"ok": True, "message": f"Provisioning '{spec.get('name') or key}' — "
            f"cloning a ~{needed // 2**30} GB install in the background. "
            f"It'll appear when ready."}


def _set_step(step: str):
    with _job_lock:
        _provision_job["step"] = step
    app_log.info("provision: %s", step)


def _run_clone_job(spec, key, game, src, dst, ports, siblings=()):
    try:
        _set_step("cloning install (copying files)")
        # cp -a: preserve perms/symlinks/timestamps. Copy into a temp then rename
        # so a crash can't leave a half-populated dst that looks complete.
        tmp = dst + ".partial"
        if os.path.exists(tmp):
            shutil.rmtree(tmp, ignore_errors=True)
        r = subprocess.run(["cp", "-a", src, tmp], capture_output=True, text=True, timeout=3600)
        if r.returncode != 0:
            raise ActionError(f"clone failed: {(r.stderr or r.stdout).strip()[:200]}")
        # Fresh world: drop the copied saves/crash dumps/logs (Palworld layout).
        for sub in ("Pal/Saved/SaveGames", "Pal/Saved/Crashes", "Pal/Saved/Logs"):
            shutil.rmtree(os.path.join(tmp, sub), ignore_errors=True)
        os.replace(tmp, dst)

        _set_step("configuring")
        spec = dict(spec)
        spec["install_dir"] = dst
        fields = game.provision(spec, ports)
        fields["_siblings"] = list(siblings)
        fields["port_map"] = dict(ports)
        display = (spec.get("name") or fields.get("server_name") or key).strip()
        name = f"{game.label} · {display}"
        note = _register(key, game.kind, name, fields, bool(spec.get("start")))

        with _job_lock:
            _provision_job.update({"state": "done", "ok": True, "name": name,
                                   "finished_ts": time.time(),
                                   "message": f"Added '{name}'.{note}"})
        app_log.info("provision %s: done", key)
    except Exception as e:
        app_log.exception("provision %s crashed", key)
        shutil.rmtree(dst + ".partial", ignore_errors=True)
        with _job_lock:
            _provision_job.update({"state": "failed", "ok": False,
                                   "finished_ts": time.time(), "message": str(e)})


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
    """Path of a gamedash-managed server's generated run script, validated.

    Only a managed server whose unit's ExecStart points at its own
    `gamedash-<key>-run.sh` is editable — this excludes legacy servers and
    custom services (whose ExecStart is an arbitrary command, not our script).
    """
    e = store.get(key)
    if not e:
        raise ActionError(f"No gamedash-managed server with key '{key}'.")
    if e.get("managed") != "gamedash":
        raise ActionError("Only gamedash-managed servers have an editable launch script.")
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
            or os.path.basename(token) != f"gamedash-{key}-run.sh"
            or not os.path.isfile(token)):
        raise ActionError("This server has no editable gamedash launch script "
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
        raise ActionError(f"No gamedash-managed server with key '{key}'.")
    if e.get("managed") != "gamedash":
        raise ActionError("Refusing to remove a legacy (hand-made) server.")
    unit = e.get("unit", _unit_name(key))
    try:
        _systemctl("disable", "--now", unit, timeout=130)
    except ActionError:
        pass  # may already be stopped/disabled
    path = _unit_path(key)
    if os.path.exists(path):
        os.remove(path)
    _systemctl("daemon-reload")
    group = e.get("slot_group")
    store.remove(key)
    if group:   # a "shared" group of one would show its last member as parked forever
        left = [x["key"] for x in store.load() if x.get("slot_group") == group]
        if len(left) == 1:
            store.update(left[0], slot_group="")
    # A Windows-only server's private Wine environment (~1 GB) holds no saves — remove it too.
    extra = ""
    from games import common
    prefix = common.wine_prefix(e.get("kind", ""), key)
    if e.get("kind") and os.path.basename(prefix).startswith(".wine-gd-") and os.path.isdir(prefix):
        shutil.rmtree(prefix, ignore_errors=True)
        extra = " Its Wine environment was deleted."
    audit_log.info("server REMOVED key=%s unit=%s%s", key, unit, " (wine prefix deleted)" if extra else "")
    return {"ok": True, "message": f"Removed '{e.get('name', key)}'.{extra} (Save data, if any, left on disk.)"}
