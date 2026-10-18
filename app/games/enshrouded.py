"""Enshrouded game type. The dedicated server is Windows-only and runs under Wine.

Settings are keys of enshrouded_server.json, which the server reads from the
folder it is started in — so each server gets its own folder of links to the
shared download plus its own settings file and savegame. The server fills in
every setting we don't write (difficulty factors and so on) with its default.
Player numbers come from the Steam query port.
"""
from __future__ import annotations

import json
import os

from games import common
from games.winegames import WineGame

EXE = "enshrouded_server.exe"
PRESETS = [["Default", "Default"], ["Relaxed", "Relaxed (easier)"], ["Hard", "Hard"],
           ["Survival", "Survival (hunger, tougher enemies)"]]

class EnshroudedGame(WineGame):
    kind = "enshrouded"
    label = "Enshrouded"
    steam_app = 2278520
    exe = EXE
    install_gb = 9
    ram_note = "about 6-8 GB of memory"
    about = "Co-op survival and building in a fog-covered world. The server is Windows-only, so it runs through Wine."
    query_on_game_port = True
    # no graceful shutdown under Wine — the game's own autosave is the save
    port_layout = [
        {"name": "game", "klass": "game", "start": 15637, "proto": "UDP", "forward": True,
         "label": "Game port (UDP)", "help": "The port players connect to. Forward it (UDP)."},
    ]
    extra_fields = [
        {"name": "maxplayers", "label": "Max players (1-16)", "type": "number", "min": 1, "max": 16,
         "default": 8},
        {"name": "preset", "label": "Difficulty", "type": "select", "options": PRESETS, "default": "Default"},
        {"name": "text_chat", "label": "Text chat", "type": "checkbox", "default": True},
        {"name": "voice_chat", "label": "Voice chat", "type": "checkbox", "default": False},
    ]
    provision_hint = ("Enshrouded — a new world in its own folder (a Windows server, run through Wine). "
                      "Friends join with the shared join password; the shared admin password gives "
                      "kick/ban rights in-game. The detailed difficulty settings start at the chosen "
                      "preset and live in the server's enshrouded_server.json. Its first start takes "
                      "a minute longer while its Wine environment (about 1 GB) is created.")

    def command(self, spec, ports, name, server_dir, install):
        return f"wine ./{EXE}"

    def write_files(self, spec, ports, name, server_dir, install):
        full = {"canKickBan": True, "canAccessInventories": True, "canEditWorld": True,
                "canEditBase": True, "canExtendBase": True, "reservedSlots": 0}
        cfg = {
            "name": name,
            "saveDirectory": "./savegame", "logDirectory": "./logs",
            "ip": "0.0.0.0", "queryPort": ports["game"],
            "slotCount": self.option(spec, "maxplayers"),
            "enableVoiceChat": self.option(spec, "voice_chat"),
            "enableTextChat": self.option(spec, "text_chat"),
            "gameSettingsPreset": self.option(spec, "preset"),
            "userGroups": [
                {"name": "Admin", "password": "set-at-launch", **full},
                {"name": "Friend", "password": "set-at-launch", **{**full, "canKickBan": False}},
            ],
        }
        common.link_farm(install, server_dir, {"enshrouded_server.json", "savegame", "logs"})
        common.write_private(self._cfg(server_dir), json.dumps(cfg, indent="\t"))   # will hold both passwords

    def sync_lines(self, spec, ports, name, server_dir, install):
        return common.json_password_sync(
            self._cfg(server_dir), [], indent="\t",
            # the passwords belong to the "Friend" and "Admin" player groups
            extra=("for g in d.get('userGroups', []):\n"
                   "    if g.get('name') == 'Admin':\n"
                   "        g['password'] = admin\n"
                   "    elif g.get('name') == 'Friend':\n"
                   "        g['password'] = join\n"))

    @staticmethod
    def _cfg(server_dir):
        return os.path.join(server_dir, "enshrouded_server.json")

    def work_dir(self, server_dir, install):
        return server_dir      # it reads its settings from the folder it runs in

    def save_dir(self, server_dir, install):
        return os.path.join(server_dir, "savegame")

    def proc_pattern(self, spec, ports, server_dir):
        return f"worldcradle-servers\\{spec['key']}\\{EXE}"
