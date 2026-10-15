"""registry.py — unified game-server registry for the dashboard.

Server definitions live in servers.json (see store.py); this module turns them
into Server objects, resolving password references from the secrets file.

Each Server describes how to: identify its systemd user unit, find its process,
query players (RCON and/or A2S), and check reachability.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field

import config


def load_secrets() -> dict:
    """Parse the central secrets file (KEY="value" lines) — path from config
    (default ~/Scripts/secrets.conf). Optional; missing file → {}."""
    out: dict[str, str] = {}
    try:
        for line in open(config.secrets_path(), encoding="utf-8"):
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            v = v.strip()
            if v[:1] in ('"', "'"):           # quoted value: take up to the closing quote
                end = v.find(v[0], 1)
                v = v[1:end] if end != -1 else v[1:]
            else:                              # bare value: drop any trailing # comment
                v = v.split("#", 1)[0].strip()
            out[k.strip()] = v
    except OSError:
        pass
    return out


def _resolve(text: str, secrets: dict) -> str:
    """Substitute ${VAR} / $VAR references using the secrets registry."""
    return re.sub(r"\$\{(\w+)\}|\$(\w+)",
                  lambda m: secrets.get(m.group(1) or m.group(2), m.group(0)), text)


def game_admin_password() -> str:
    """The shared admin/RCON password from the central registry."""
    return load_secrets().get("GAME_ADMIN_PASSWORD", "")


def write_secrets(updates: dict) -> None:
    """Set KEY="value" entries in the secrets file, preserving every other line
    (comments, other keys, ordering). Creates the file (0600) if missing. The
    file is sourced by bash run scripts, so callers must validate values are
    shell-safe before calling (no quotes/$/backtick/whitespace)."""
    import os as _os
    path = config.secrets_path()
    try:
        lines = open(path, encoding="utf-8").read().splitlines()
    except OSError:
        lines = []
    pending = dict(updates)
    out = []
    for line in lines:
        m = re.match(r"\s*([A-Za-z_][A-Za-z0-9_]*)\s*=", line)
        if m and m.group(1) in pending:
            k = m.group(1)
            out.append(f'{k}="{pending.pop(k)}"')
        else:
            out.append(line)
    for k, v in pending.items():
        out.append(f'{k}="{v}"')
    tmp = path + ".tmp"
    _os.makedirs(_os.path.dirname(path), exist_ok=True)
    fd = _os.open(tmp, _os.O_WRONLY | _os.O_CREAT | _os.O_TRUNC, 0o600)
    with _os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write("\n".join(out) + "\n")
    _os.replace(tmp, path)


@dataclass
class Server:
    key: str                      # short id, also used in URLs
    name: str                     # display name
    kind: str                     # ark | palworld | valheim | satisfactory
    unit: str                     # systemd --user unit
    game_port: int                # UDP game port
    query_port: int | None        # UDP Steam A2S query port (None if none)
    rcon_port: int | None = None  # TCP RCON port, loopback only (None if none)
    rcon_password: str | None = None
    a2s: bool = False             # does this server actually answer A2S queries?
    proc_match: str = ""          # substring expected in the process cmdline
    # ARK maps that reuse the same ports are mutually exclusive. Servers that
    # share a slot carry the same non-empty group id; only one runs at a time.
    slot_group: str = ""
    map_code: str = ""            # ARK map code (info only)
    save_dir: str = ""            # ARK save dir (info only)
    log_path: str = ""            # log file to parse for players (Valheim)
    server_name: str = ""         # the actual in-game/session name players see
    join_port: int | None = None  # the port friends connect to (ARK: query; else game)
    steam_app: int | None = None  # Steam dedicated-server app id (for update checks)
    install_dir: str = ""         # game install dir (contains steamapps/appmanifest)
    managed: str = "legacy"       # "legacy" (hand-made unit) | "gamedash" (provisioned)
    # ---- save-location fields (drive backup/restore via GameType.save_paths) --
    save_root: str = ""           # absolute base save dir (Valheim savedir / Satisfactory SaveGames / custom folder)
    world: str = ""               # Valheim world name (its save files are <world>.db/.fwl)
    cluster_id: str = ""          # ARK cluster id (its shared cluster dir is also backed up)
    backup_keep: int = 5          # how many backups to retain for this server (prune oldest)
    # ports the server binds beyond game/query/rcon (e.g. a second shard, Steam
    # ports) — tracked so nothing else is handed the same number
    extra_ports: list = field(default_factory=list)
    port_map: dict = field(default_factory=dict)   # layout name -> port, for servers made here

    def all_ports(self) -> set[int]:
        mine = {int(p) for p in (self.game_port, self.query_port, self.rcon_port) if p}
        mine |= {int(p) for p in self.extra_ports if p}
        if self.kind in ("ark", "valheim") and self.game_port:
            mine.add(int(self.game_port) + 1)   # both also bind game port + 1
        return mine

    @property
    def has_rcon(self) -> bool:
        return bool(self.rcon_port and self.rcon_password)

    @property
    def has_a2s(self) -> bool:
        return self.a2s and self.query_port is not None


def _expand(p: str) -> str:
    return os.path.expanduser(p) if p else ""


def _load_store(secrets: dict) -> list[Server]:
    """Build Server objects from the servers.json store (non-ARK + any servers
    added via the dashboard). Passwords come from secrets.conf via a *_ref."""
    import store
    out: list[Server] = []
    for e in store.load():
        try:
            rp = e.get("rcon_password") or secrets.get(e.get("rcon_password_ref", ""), "")
            out.append(Server(
                key=e["key"], name=e["name"], kind=e["kind"], unit=e["unit"],
                game_port=int(e["game_port"]),
                query_port=e.get("query_port"),
                rcon_port=e.get("rcon_port"),
                rcon_password=rp or None,
                a2s=bool(e.get("a2s", False)),
                proc_match=e.get("proc_match", ""),
                server_name=e.get("server_name", ""),
                join_port=e.get("join_port"),
                steam_app=e.get("steam_app"),
                install_dir=_expand(e.get("install_dir", "")),
                log_path=_expand(e.get("log_path", "")),
                managed=e.get("managed", "gamedash"),
                slot_group=e.get("slot_group", ""),
                save_dir=e.get("save_dir", ""),
                save_root=_expand(e.get("save_root", "")),
                world=e.get("world", ""),
                cluster_id=e.get("cluster_id", ""),
                backup_keep=int(e.get("backup_keep") or 5),
                extra_ports=[int(p) for p in (e.get("extra_ports") or [])],
                port_map=dict(e.get("port_map") or {}),
            ))
        except (KeyError, ValueError, TypeError):
            continue  # skip a malformed entry rather than break the whole list
    return out


def load_servers() -> list[Server]:
    servers = _load_store(load_secrets())
    # Sort by game name then world name. Display names are "Game · World"
    # (e.g. "ARK · Aberration"); Satisfactory has no world part.
    def sort_key(s: Server):
        parts = s.name.split(" · ", 1)
        game = parts[0]
        world = parts[1] if len(parts) > 1 else ""
        return (game.lower(), world.lower())
    return sorted(servers, key=sort_key)


def by_key() -> dict[str, Server]:
    return {s.key: s for s in load_servers()}


if __name__ == "__main__":
    for s in load_servers():
        slot = f"  [slot {s.slot_group}]" if s.slot_group else ""
        rc = f"rcon {s.rcon_port}" if s.has_rcon else "no-rcon"
        a2 = f"a2s {s.query_port}" if s.has_a2s else "no-a2s"
        print(f"{s.key:12} {s.kind:12} {s.unit:22} game {s.game_port:5}  {rc:10} {a2}{slot}")
