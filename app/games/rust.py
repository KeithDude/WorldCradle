"""Rust game type (native Linux dedicated server).

Everything is set on the launch line as "+server.<setting> value". Each server
has its own identity folder (world + player data) under the install. Rust has
no join password. Player numbers come from the Steam query port.
"""
from __future__ import annotations

import os

import monitor
from games.base import empty_probe, safe_name
from games.simple import SimpleGame

EXE = "RustDedicated"

class RustGame(SimpleGame):
    kind = "rust"
    label = "Rust"
    steam_app = 258550
    exe = EXE
    servers_folder = "server"
    install_gb = 7
    ram_note = "about 8-12 GB of memory; more for big maps and many players"
    about = "Open-world survival and raiding. Heavy: slow first start and lots of memory."
    stop_seconds = 90            # the stop signal makes the server save and quit

    port_layout = [
        {"name": "game", "klass": "game", "start": 28015, "proto": "UDP", "forward": True,
         "label": "Game port (UDP)", "help": "The port players connect to. Forward it."},
        {"name": "query", "klass": "query", "start": 28017, "proto": "UDP", "forward": True,
         "label": "Steam query port (UDP)", "help": "Lists the server in the browser. Forward it."},
        # its web admin console (the dashboard doesn't use it; it listens on this computer only)
        {"name": "webrcon", "klass": "rcon", "start": 28016, "proto": "TCP", "label": "Admin console port (TCP)",
         "form": False},
        {"name": "app", "klass": "query", "start": 28082, "proto": "TCP", "forward": True,
         "label": "Rust+ companion app port (TCP)",
         "help": "Only needed if players use the Rust+ phone app with this server."},
    ]
    extra_fields = [
        {"name": "maxplayers", "label": "Max players (1-500)", "type": "number", "min": 1, "max": 500,
         "default": 20},
        {"name": "worldsize", "label": "Map size (1000-6000; 3000 suits a small group)", "type": "number",
         "min": 1000, "max": 6000, "step": 500, "default": 3000,
         "help": "Bigger maps take longer to create and use more memory."},
        {"name": "seed", "label": "Map seed — a number; blank = random", "type": "number",
         "min": 1, "max": 2147483647, "placeholder": "random"},
        {"name": "description", "label": "Description shown in the server browser — optional",
         "placeholder": ""},
    ]
    provision_hint = ("Rust — a new map with its own save folder. Rust servers have no join password: "
                      "anyone who finds the server can join. The first start creates the map and can "
                      "take 5-10 minutes before the server appears.")

    def server_folder(self, install, key):
        return os.path.join(install, self.servers_folder, "wc_" + key.replace("-", "_"))

    def command(self, spec, ports, name, server_dir, install):
        seed = self.option(spec, "seed")
        if seed is None:
            seed = int.from_bytes(os.urandom(4), "big") % 2147483646 + 1
        return (f'./{EXE} -batchmode -nographics -logfile "{self.log_file(server_dir, install)}" \\\n'
                f'    +server.identity "{os.path.basename(server_dir)}" \\\n'
                f'    +server.port {ports["game"]} +server.queryport {ports["query"]} \\\n'
                f'    +rcon.ip 127.0.0.1 +rcon.port {ports["webrcon"]} +rcon.password "$GAME_ADMIN_PASSWORD" +rcon.web 1 \\\n'
                f'    +app.port {ports["app"]} \\\n'
                f'    +server.hostname "{name}" +server.description "{safe_name(spec.get("description") or "", 200)}" \\\n'
                f'    +server.maxplayers {self.option(spec, "maxplayers")} +server.level "Procedural Map" \\\n'
                f'    +server.worldsize {self.option(spec, "worldsize")} +server.seed {seed} +server.saveinterval 300')

    def pre(self, spec, ports, name, server_dir, install):
        return f'export LD_LIBRARY_PATH="$LD_LIBRARY_PATH:{install}/RustDedicated_Data/Plugins/x86_64"\n'

    def log_file(self, server_dir, install):
        return os.path.join(server_dir, "server.log")

    def proc_pattern(self, spec, ports, server_dir):
        return f"+server.identity {os.path.basename(server_dir)}"

    def probe(self, s) -> dict:
        out = empty_probe()
        info = monitor.a2s_info(s.query_port) if s.query_port else None
        if info is not None:
            names = monitor.a2s_player_names(s.query_port) if info["players"] else []
            out.update(reachable=True, players=info["players"], max_players=info["max_players"],
                       player_names=names, player_detail=[{"name": n, "id": ""} for n in names])
        return out
