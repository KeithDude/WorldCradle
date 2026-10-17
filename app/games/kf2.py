"""Killing Floor 2 — a native Linux server, built on games/simple.py (SimpleGame)."""
from __future__ import annotations

import re

from games.simple import GAME_PORT_HELP, QUERY_PORT_HELP, SimpleGame, port


class Kf2Game(SimpleGame):
    kind = "kf2"
    label = "Killing Floor 2"
    steam_app = 232130
    exe = "Binaries/Win64/KFGameSteamServer.bin.x86_64"
    install_gb = 25
    ram_note = "about 2-3 GB of memory"
    about = "Co-op wave shooter against monsters, up to 6 players."
    port_layout = [port("game", 7790, "Game port (UDP)", help=GAME_PORT_HELP),
                   port("query", 27170, "Steam query port (UDP)", help=QUERY_PORT_HELP),
                   port("web", 8090, "Web admin port (TCP)", proto="TCP", forward=False, klass="rcon",
                        form=False)]
    MAPS = ["KF-BioticsLab", "KF-BurningParis", "KF-Outpost", "KF-VolterManor", "KF-Catacombs",
            "KF-EvacuationPoint", "KF-Farmhouse", "KF-BlackForest", "KF-ContainmentStation", "KF-Prison"]
    DIFFICULTIES = [["0", "Normal"], ["1", "Hard"], ["2", "Suicidal"], ["3", "Hell on Earth"]]
    LENGTHS = [["0", "Short (4 waves)"], ["1", "Medium (7 waves)"], ["2", "Long (10 waves)"]]
    provision_hint = ("Killing Floor 2 — everything is set when the server starts; there is no saved "
                      "world. The join and admin passwords are the shared ones.")

    @property
    def extra_fields(self) -> list[dict]:
        return [{"name": "map", "label": "Starting map", "type": "select", "default": "KF-BioticsLab",
                 "options": [[m, m[3:]] for m in self.MAPS]},
                {"name": "difficulty", "label": "Difficulty", "type": "select", "default": "0",
                 "options": self.DIFFICULTIES},
                {"name": "length", "label": "Game length", "type": "select", "default": "1",
                 "options": self.LENGTHS}]   # the game is always 6 players

    def command(self, spec, ports, name, server_dir, install):
        key = re.sub(r"[^A-Za-z0-9_]", "_", spec["key"])
        mapname = self.option(spec, "map")
        diff = self.option(spec, "difficulty")
        length = self.option(spec, "length")
        # ConfigSubDir gives this server its own settings folder under KFGame/Config
        return (f'./Binaries/Win64/KFGameSteamServer.bin.x86_64 "{mapname}?ConfigSubDir=rc_{key}'
                f'?Difficulty={diff}?GameLength={length}'
                f'?GamePassword=$GAME_SERVER_PASSWORD?AdminPassword=$GAME_ADMIN_PASSWORD" '
                f'-Port={ports["game"]} -QueryPort={ports["query"]} -WebAdminPort={ports["web"]} '
                f'-ServerName="\\"{name}\\""')

    def proc_pattern(self, spec, ports, server_dir):
        return f"-Port={ports['game']} -QueryPort"
