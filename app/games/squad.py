"""Squad and Squad 44 — a native Linux server, built on games/simple.py (SimpleGame)."""
from __future__ import annotations

import os
import re

import monitor
from games import common
from games.base import ActionError, empty_probe
from games.simple import RCON_PORT_HELP, SimpleGame, port


def squad_password_lines(rcon_cfg: str, rcon_port: int, set_join: bool) -> str:
    """Shell lines for Squad-engine servers: put the admin password into Rcon.cfg,
    and (optionally) lock the server with the join password once it is up — that
    can only be done through the admin console, not from a settings file."""
    out = common.password_sync(rcon_cfg, [("Password", "admin")])
    if set_join:
        out += (f"python3 - {rcon_port} \"$GAME_ADMIN_PASSWORD\" \"$GAME_SERVER_PASSWORD\" <<'LOCK' &\n"
                "import socket, struct, sys, time\n"
                "port, admin, join = int(sys.argv[1]), sys.argv[2], sys.argv[3]\n"
                "def pkt(i, kind, body):\n"
                '    b = struct.pack("<ii", i, kind) + body.encode() + b"\\0\\0"\n'
                '    return struct.pack("<i", len(b)) + b\n'
                "for _ in range(240):            # the console opens when the first map has loaded\n"
                "    time.sleep(5)\n"
                "    try:\n"
                '        s = socket.create_connection(("127.0.0.1", port), timeout=5)\n'
                "        s.sendall(pkt(1, 3, admin)); time.sleep(1); s.recv(4096)\n"
                '        s.sendall(pkt(2, 2, "AdminSetServerPassword " + join)); time.sleep(1); s.recv(4096)\n'
                "        s.close(); break\n"
                "    except OSError:\n"
                "        pass\n"
                "LOCK\n")
    return out


class SquadGame(SimpleGame):
    kind = "squad"
    label = "Squad"
    steam_app = 403240
    exe = "SquadGame/Binaries/Linux/SquadGameServer"
    project = "SquadGame"
    join_password_in_server_cfg = False     # no join-password setting in its files: it is set over the admin console
    needs_install_clone = True   # its settings folder sits beside the program files
    install_gb = 14
    ram_note = "about 6-10 GB of memory"
    about = "Large-scale 50-vs-50 military shooter built around teamwork and communication."
    kill_signal = "SIGINT"
    stop_seconds = 30            # matches, not worlds: nothing to save
    actions = {"broadcast"}
    port_layout = [port("game", 7787, "Game port (UDP, plus the next one)", span=2,
                        help="The port players connect to. Forward it and the one after it (UDP)."),
                   port("query", 27165, "Steam query port (UDP and TCP, plus the next one)", span=2,
                        proto="UDP and TCP",
                        help="Lists the server in the browser. Forward it and the one after it (UDP and TCP)."),
                   port("beacon", 15000, "Beacon port (UDP and TCP)", proto="UDP and TCP", form=False),
                   port("rcon", 21114, "Admin console port (TCP)", proto="TCP", forward=False,
                        help=RCON_PORT_HELP)]
    extra_fields = [
        {"name": "maxplayers", "label": "Max players (1-100)", "type": "number", "min": 1, "max": 100,
         "default": 40},
        {"name": "public", "label": "List in the public server browser", "type": "checkbox", "default": True},
        {"name": "locked", "label": "Require the shared join password", "type": "checkbox", "default": True},
    ]

    @property
    def provision_note(self) -> str:
        return (f"{self.label} keeps its settings beside its program files, so each server gets its own "
                f"copy of the game (about {self.install_gb} GB).")

    @property
    def provision_hint(self) -> str:
        join = ("so is the join password" if self.join_password_in_server_cfg
                else "the shared join password is applied a minute or two after the first map loads")
        return (f"{self.label} — a match server with its own copy of the game. The admin password is the "
                f"shared one; {join}. Map rotation and admins are the files in its ServerConfig folder.")

    def _cfg(self, install, name):
        return os.path.join(install, self.project, "ServerConfig", name)

    def command(self, spec, ports, name, server_dir, install):
        maxp = self.option(spec, "maxplayers")
        return (f'./{self.exe} {self.project} Port={ports["game"]} QueryPort={ports["query"]} '
                f'beaconport={ports["beacon"]} FIXEDMAXPLAYERS={maxp} RANDOM=NONE -log')

    def write_files(self, spec, ports, name, server_dir, install):
        edits = {
            "Server.cfg": (("ServerName", f'"{name}"'),
                           ("MaxPlayers", self.option(spec, "maxplayers")),
                           ("ShouldAdvertise", "true" if self.option(spec, "public") else "false")),
            # the admin console listens on this computer only
            "Rcon.cfg": (("IP", "127.0.0.1"), ("Port", ports["rcon"]), ("Password", "set-at-launch")),
        }
        for fname, pairs in edits.items():
            path = self._cfg(install, fname)
            text = open(path, encoding="utf-8-sig").read()
            for key, value in pairs:
                text = common.ini_set(text, key, value)
            common.write_private(path, text)

    def pre(self, spec, ports, name, server_dir, install):
        locked = self.option(spec, "locked")
        out = squad_password_lines(self._cfg(install, "Rcon.cfg"), ports["rcon"], locked)
        if self.join_password_in_server_cfg:
            # keep Server.cfg's own password line in step too (empty = no password)
            out += common.password_sync(self._cfg(install, "Server.cfg"),
                                        [("ServerPassword", "join" if locked else "empty")],
                                        quoted=True, add_missing=True)
        return out

    def save_dir(self, server_dir, install):
        return os.path.join(install, self.project, "ServerConfig")

    def log_file(self, server_dir, install):
        return os.path.join(install, self.project, "Saved", "Logs", f"{self.project}.log")

    def proc_pattern(self, spec, ports, server_dir):
        return f"Port={ports['game']} QueryPort"

    has_query = False   # no Steam query answer; the admin console reports players instead

    @staticmethod
    def parse_players(text: str) -> list[str]:
        """Names from the "Active Players" part of the console's ListPlayers answer."""
        active = text.split("----- Recently Disconnected", 1)[0]
        return [m.group(1).strip() for m in re.finditer(r"(?m)^ID: \d+ \|.*?\| Name: (.*?) \| Team ID:", active)]

    def probe(self, s) -> dict:
        out = empty_probe()
        text = monitor.palworld_rcon(s.rcon_port, s.rcon_password, "ListPlayers") if s.rcon_port else None
        if text is not None:
            names = self.parse_players(text)
            out.update(reachable=True, players=len(names), player_names=names,
                       player_detail=[{"name": n, "id": ""} for n in names])
            info = monitor.palworld_rcon(s.rcon_port, s.rcon_password, "ShowServerInfo") or ""
            m = re.search(r'"MaxPlayers":(\d+)', info)
            if m:
                out["max_players"] = int(m.group(1))
        return out

    def broadcast(self, s, message: str) -> str:
        r = monitor.palworld_rcon(s.rcon_port, s.rcon_password,
                                  "AdminBroadcast " + message.replace("\n", " ")[:200])
        if r is None:
            raise ActionError(f"Message to {s.name} failed (the admin console didn't answer).")
        return "sent"


class Squad44Game(SquadGame):
    kind = "squad44"
    label = "Squad 44"
    steam_app = 746200
    exe = "PostScriptum/Binaries/Linux/PostScriptumServer"
    project = "PostScriptum"
    install_gb = 35
    about = "World War II 40-vs-40 tactical shooter (formerly Post Scriptum)."
    join_password_in_server_cfg = True      # Server.cfg has ServerPassword= (Squad's does not)
    port_layout = [port("game", 10027, "Game port (UDP, plus the next one)", span=2,
                        help="The port players connect to. Forward it and the one after it (UDP)."),
                   port("query", 10037, "Steam query port (UDP and TCP, plus the next one)", span=2,
                        proto="UDP and TCP",
                        help="Lists the server in the browser. Forward it and the one after it (UDP and TCP)."),
                   port("beacon", 15010, "Beacon port (UDP)", form=False),
                   port("rcon", 21124, "Admin console port (TCP)", proto="TCP", forward=False,
                        help=RCON_PORT_HELP)]
    extra_fields = [
        {"name": "maxplayers", "label": "Max players (1-80)", "type": "number", "min": 1, "max": 80,
         "default": 40},
        {"name": "public", "label": "List in the public server browser", "type": "checkbox", "default": True},
        {"name": "locked", "label": "Require the shared join password", "type": "checkbox", "default": True},
    ]
