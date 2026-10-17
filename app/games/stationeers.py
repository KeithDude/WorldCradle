"""Stationeers — a native Linux server, built on games/simple.py (SimpleGame)."""
from __future__ import annotations

import os

from games.simple import GAME_PORT_HELP, SimpleGame, port


STATIONEERS_WORLDS = [["Lunar", "The Moon"], ["Mars2", "Mars"], ["Europa3", "Europa"],
                      ["MimasHerschel", "Mimas"], ["Venus", "Venus"], ["Vulcan2", "Vulcan"]]


class StationeersGame(SimpleGame):
    kind = "stationeers"
    label = "Stationeers"
    steam_app = 600760
    exe = "rocketstation_DedicatedServer.x86_64"
    install_gb = 5
    ram_note = "about 3-6 GB of memory; grows with the size of the base"
    about = "Hardcore space-station building and survival with detailed physics and atmospherics."
    has_query = False        # doesn't answer the Steam query, so no player count
    stop_seconds = 45
    port_layout = [port("game", 27510, "Game port (UDP)", help=GAME_PORT_HELP),
                   port("update", 27511, "Update port (UDP)", klass="query",
                        help="The game's second port. Forward it (UDP) alongside the game port.")]
    extra_fields = [
        {"name": "world", "label": "World", "type": "select", "options": STATIONEERS_WORLDS,
         "default": "Lunar"},
        {"name": "maxplayers", "label": "Max players (1-20)", "type": "number", "min": 1, "max": 20,
         "default": 10},
        {"name": "public", "label": "List in the public server browser", "type": "checkbox", "default": True},
        {"name": "autosave", "label": "Autosave every … seconds (60-3600)", "type": "number", "min": 60,
         "max": 3600, "default": 300},
        {"name": "pause_empty", "label": "Pause the world when nobody is online", "type": "checkbox",
         "default": True},
    ]
    provision_hint = ("Stationeers — a new world in its own save. The join password is the shared one. "
                      "The server has no “save now” command, so stopping it can lose up to one "
                      "autosave interval of progress; the dashboard can't show its player count.")

    @staticmethod
    def _save(server_dir):
        return "gd_" + os.path.basename(server_dir).replace("-", "_")

    def command(self, spec, ports, name, server_dir, install):
        world = self.option(spec, "world")
        return (f'./{self.exe} -batchmode -nographics -logFile "{self.log_file(server_dir, install)}" '
                f'-settingspath "{server_dir}/setting.xml" -load {self._save(server_dir)} {world} '
                f'-settings StartLocalHost true LocalIpAddress 0.0.0.0 UPNPEnabled false UseSteamP2P false '
                f'ServerVisible {"true" if self.option(spec, "public") else "false"} '
                f'GamePort {ports["game"]} UpdatePort {ports["update"]} '
                f'ServerName "{name}" ServerPassword "$GAME_SERVER_PASSWORD" '
                f'ServerMaxPlayers {self.option(spec, "maxplayers")} '
                f'AutoSave true SaveInterval {self.option(spec, "autosave")} '
                f'AutoPauseServer {"true" if self.option(spec, "pause_empty") else "false"}')

    def save_dir(self, server_dir, install):
        return os.path.join(install, "saves", self._save(server_dir))

    def log_file(self, server_dir, install):
        return os.path.join(server_dir, "server.log")
