"""V Rising game type. The dedicated server is Windows-only and runs under Wine.

Each server keeps its settings and saves in its own data folder (the launcher's
-persistentDataPath). Setting names are keys of ServerHostSettings.json; the
file is copied from the one shipped with the installed version so every other
default is right. Player numbers come from the Steam query port; messages go
through the game's RCON console.
"""
from __future__ import annotations

import json
import os

from games import common
from games.base import ActionError, safe_name
from games.simple import RCON_PORT_HELP
from games.winegames import WineGame, win

EXE = "VRisingServer.exe"
_SETTINGS = "VRisingServer_Data/StreamingAssets/Settings"
PRESETS = [["StandardPvE", "Standard PvE (players vs the world)"], ["StandardPvP", "Standard PvP"],
           ["HardcorePvP", "Hardcore PvP (full loot)"], ["DuoPvP", "Duo PvP (clans of two)"],
           ["SoloPvP", "Solo PvP"]]

class VRisingGame(WineGame):
    kind = "vrising"
    label = "V Rising"
    steam_app = 1829350
    requires = ["wine", "xvfb-run"]
    exe = EXE
    install_gb = 2
    ram_note = "about 4-8 GB of memory"
    about = "Vampire survival and castle building. The server is Windows-only, so it runs through Wine."
    rcon_commands = {"broadcast": "announce {message}"}
    # no graceful shutdown under Wine — the game autosaves every two minutes
    port_layout = [
        {"name": "game", "klass": "game", "start": 9876, "proto": "UDP", "forward": True,
         "label": "Game port (UDP)", "help": "The port players connect to. Forward it (UDP)."},
        {"name": "query", "klass": "query", "start": 9877, "proto": "UDP", "forward": True,
         "label": "Steam query port (UDP)", "help": "Lists the server in the browser. Forward it (UDP)."},
        {"name": "rcon", "klass": "rcon", "start": 25600, "proto": "TCP", "label": "Admin console port (TCP)",
         "help": RCON_PORT_HELP},
    ]
    extra_fields = [
        {"name": "preset", "label": "Rules", "type": "select", "options": PRESETS, "default": "StandardPvE"},
        {"name": "maxplayers", "label": "Max players (1-128)", "type": "number", "min": 1, "max": 128,
         "default": 10},
        {"name": "description", "label": "Description shown in the server list — optional", "placeholder": ""},
        {"name": "listed", "label": "List in the public server browser", "type": "checkbox", "default": True,
         "help": "When this is off the server doesn't answer Steam's query either, so the dashboard "
                 "can't show how many players are on."},
    ]
    provision_hint = ("V Rising — a new world in its own folder (a Windows server, run through Wine). The "
                      "join password is the shared one. The detailed rules start from the chosen preset "
                      "and live in the server's ServerGameSettings.json. Its first start takes a minute "
                      "longer while its Wine environment (about 1 GB) is created.")

    def command(self, spec, ports, name, server_dir, install):
        if not os.path.isdir(os.path.join(install, _SETTINGS)):
            raise ActionError(f"V Rising isn't installed ({install}).")
        preset = self.option(spec, "preset")
        if not os.path.isfile(os.path.join(install, "VRisingServer_Data/StreamingAssets/GameSettingPresets",
                                           preset + ".json")):
            raise ActionError(f"This version of V Rising doesn't have the “{preset}” rules.")
        # The server refuses to start without a display ("Failed to create batch mode
        # window"), so it gets an invisible virtual one.
        return (f'xvfb-run -a -s "-screen 0 640x480x24 -nolisten tcp" wine ./{EXE} '
                f'-persistentDataPath "{win(server_dir)}" -logFile "{win(self.log_file(server_dir, install))}"')

    def write_files(self, spec, ports, name, server_dir, install):
        listed = self.option(spec, "listed")
        host = json.load(open(os.path.join(install, _SETTINGS, "ServerHostSettings.json"), encoding="utf-8-sig"))
        host.update({
            "Name": name, "Description": safe_name(spec.get("description") or "", 200),
            "Port": ports["game"], "QueryPort": ports["query"],
            "MaxConnectedUsers": self.option(spec, "maxplayers"),
            "SaveName": "world", "Password": "set-at-launch",
            "ListOnSteam": listed, "ListOnEOS": listed,
            "GameSettingsPreset": self.option(spec, "preset"),
            "Rcon": {"Enabled": True, "Port": ports["rcon"], "Password": "set-at-launch"},
        })
        os.makedirs(os.path.join(server_dir, "Settings"), exist_ok=True)
        common.write_private(self._host(server_dir), json.dumps(host, indent=2))   # will hold both passwords

    def sync_lines(self, spec, ports, name, server_dir, install):
        return common.json_password_sync(self._host(server_dir),
                                         [(("Password",), "join"), (("Rcon", "Password"), "admin")])

    @staticmethod
    def _host(server_dir):
        return os.path.join(server_dir, "Settings", "ServerHostSettings.json")

    def save_dir(self, server_dir, install):
        return os.path.join(server_dir, "Saves")

    def log_file(self, server_dir, install):
        return os.path.join(server_dir, "VRisingServer.log")

