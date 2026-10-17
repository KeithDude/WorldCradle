"""Arma Reforger — a native Linux server, built on games/simple.py (SimpleGame)."""
from __future__ import annotations

import os

from games import common
from games.simple import GAME_PORT_HELP, QUERY_PORT_HELP, SimpleGame, port


class ArmaReforgerGame(SimpleGame):
    kind = "armareforger"
    label = "Arma Reforger"
    steam_app = 1874900
    exe = "ArmaReforgerServer"
    install_gb = 9
    ram_note = "about 4-8 GB of memory"
    about = "Military sandbox with large-scale Conflict battles and a Game Master mode."
    kill_signal = "SIGTERM"
    port_layout = [port("game", 2001, "Game port (UDP)", help=GAME_PORT_HELP),
                   port("query", 17777, "Steam query port (UDP)", help=QUERY_PORT_HELP)]
    SCENARIOS = [["{ECC61978EDCC2B5A}Missions/23_Campaign.conf", "Conflict — Everon"],
                 ["{59AD59368755F41A}Missions/21_GM_Eden.conf", "Game Master — Everon"]]
    extra_fields = [
        {"name": "scenario", "label": "Scenario", "type": "select", "options": SCENARIOS,
         "default": SCENARIOS[0][0]},
        {"name": "maxplayers", "label": "Max players (1-128)", "type": "number", "min": 1, "max": 128,
         "default": 16},
        {"name": "visible", "label": "List in the public server browser", "type": "checkbox", "default": True},
        {"name": "battleye", "label": "BattlEye anti-cheat", "type": "checkbox", "default": True},
        {"name": "crossplay", "label": "Allow Xbox players (crossplay)", "type": "checkbox", "default": True},
    ]
    provision_hint = ("Arma Reforger — a new server with its own settings and profile folder. The join and "
                      "admin passwords are the shared ones (log in as admin in-game with #login and the "
                      "admin password).")

    def command(self, spec, ports, name, server_dir, install):
        self.option(spec, "scenario")
        self.option(spec, "maxplayers")
        return (f'./ArmaReforgerServer -config "{server_dir}/config.json" -profile "{server_dir}/profile" '
                f"-maxFPS 60 -nothrow")

    def write_files(self, spec, ports, name, server_dir, install):
        import json
        cfg = {
            "bindAddress": "0.0.0.0", "bindPort": ports["game"], "publicPort": ports["game"],
            "a2s": {"address": "0.0.0.0", "port": ports["query"]},
            "game": {
                "name": name, "password": "set-at-launch", "passwordAdmin": "set-at-launch",
                "scenarioId": self.option(spec, "scenario"),
                "maxPlayers": self.option(spec, "maxplayers"),
                "visible": self.option(spec, "visible"),
                "crossPlatform": self.option(spec, "crossplay"),
                "gameProperties": {"battlEye": self.option(spec, "battleye")},
            },
        }
        common.write_private(os.path.join(server_dir, "config.json"), json.dumps(cfg, indent=2))
        os.makedirs(os.path.join(server_dir, "profile"), exist_ok=True)

    def pre(self, spec, ports, name, server_dir, install):
        return common.json_password_sync(os.path.join(server_dir, "config.json"),
                                         [(("game", "password"), "join"), (("game", "passwordAdmin"), "admin")])

    def save_dir(self, server_dir, install):
        return os.path.join(server_dir, "profile")
