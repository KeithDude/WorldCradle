"""Sons of the Forest game type. The dedicated server is Windows-only and runs under Wine.

Each server keeps its settings and saves in its own folder (the server's
-userdatapath option). Setting names are keys of dedicatedserver.cfg. Player
numbers come from the Steam query port; there is no remote console.
"""
from __future__ import annotations

import json
import os

from games import common
from games.winegames import WineGame, win

EXE = "SonsOfTheForestDS.exe"
GAME_APPID = "1326470"   # the game's own App ID; the server insists on a steam_appid.txt holding it
MODES = [["Normal", "Normal"], ["Hard", "Hard"], ["HardSurvival", "Hard survival"],
         ["Peaceful", "Peaceful (no enemies)"]]

class SotfGame(WineGame):
    kind = "sotf"
    label = "Sons of the Forest"
    steam_app = 2465200
    requires = ["wine", "xvfb-run"]
    exe = EXE
    install_gb = 4
    ram_note = "about 4-8 GB of memory"
    about = "Survival horror on a cannibal island, up to 8 players. Runs through Wine."
    # no graceful shutdown under Wine — the game autosaves every 10 minutes
    port_layout = [
        {"name": "game", "klass": "game", "start": 8766, "proto": "UDP", "forward": True,
         "label": "Game port (UDP)", "help": "The port players connect to. Forward it (UDP)."},
        {"name": "query", "klass": "query", "start": 27090, "proto": "UDP", "forward": True,
         "label": "Steam query port (UDP)", "help": "Lists the server in the browser. Forward it (UDP)."},
        {"name": "blob", "klass": "game", "start": 9700, "proto": "UDP", "forward": True,
         "label": "World-sync port (UDP)", "help": "Used to send the world to joining players. Forward it (UDP)."},
    ]
    extra_fields = [
        {"name": "maxplayers", "label": "Max players (1-8)", "type": "number", "min": 1, "max": 8,
         "default": 8},
        {"name": "mode", "label": "Difficulty", "type": "select", "options": MODES, "default": "Normal"},
        {"name": "lan_only", "label": "Home network only (not listed on the internet)", "type": "checkbox",
         "default": False},
    ]
    provision_hint = ("Sons of the Forest — a new save in its own folder (a Windows server, run through "
                      "Wine). The join password is the shared one. To be an admin in-game, add your "
                      "Steam ID to the server's ownerswhitelist.txt. Its first start takes a minute "
                      "longer while its Wine environment (about 1 GB) is created.")

    def command(self, spec, ports, name, server_dir, install):
        self.option(spec, "maxplayers")
        # The server needs a display to start, so it gets an invisible virtual one.
        return f'xvfb-run -a -s "-screen 0 640x480x24 -nolisten tcp" wine ./{EXE} -userdatapath "{win(server_dir)}"'

    def write_files(self, spec, ports, name, server_dir, install):
        cfg = {
            "IpAddress": "0.0.0.0", "GamePort": ports["game"], "QueryPort": ports["query"],
            "BlobSyncPort": ports["blob"], "ServerName": name,
            "MaxPlayers": self.option(spec, "maxplayers"),
            "Password": "set-at-launch", "LanOnly": self.option(spec, "lan_only"),
            "SaveSlot": 1, "SaveMode": "Continue",
            "GameMode": self.option(spec, "mode"),
            "SaveInterval": 600, "IdleDayCycleSpeed": 0.0, "IdleTargetFramerate": 5,
            "ActiveTargetFramerate": 60, "LogFilesEnabled": True, "TimestampLogFilenames": False,
            "TimestampLogEntries": True,
            # its self-test expects UPnP/outside reachability and refuses to start without it
            "SkipNetworkAccessibilityTest": True,
            "GameSettings": {}, "CustomGameModeSettings": {},
        }
        common.write_private(self._cfg(server_dir), json.dumps(cfg, indent=2))   # will hold the join password
        # Without this file the first start only creates it, says "restart" and hangs.
        with open(os.path.join(server_dir, "ownerswhitelist.txt"), "w", encoding="utf-8") as f:
            f.write("# In-game admins: one Steam ID (the long number, SteamID64) per line.\n"
                    "# Lines starting with # are ignored.\n")
        appid = os.path.join(install, "steam_appid.txt")
        if not os.path.exists(appid):   # otherwise the first start only creates it and quits
            with open(appid, "w", encoding="utf-8") as f:
                f.write(GAME_APPID)

    def sync_lines(self, spec, ports, name, server_dir, install):
        return common.json_password_sync(self._cfg(server_dir), [(("Password",), "join")])

    @staticmethod
    def _cfg(server_dir):
        return os.path.join(server_dir, "dedicatedserver.cfg")

    def proc_pattern(self, spec, ports, server_dir):
        return f"realmcradle-servers\\{spec['key']}"     # its -userdatapath argument
