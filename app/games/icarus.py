"""Icarus game type. The dedicated server is Windows-only and runs under Wine.

Each server keeps its settings and saves in its own folder (the server's
-UserDir option). Setting names are keys of ServerSettings.ini. Player numbers
come from the Steam query port; there is no remote console — admins use the
in-game chat commands after "/AdminLogin <admin password>".
"""
from __future__ import annotations

import os

from games import common
from games.base import opt_bool
from games.winegames import WineGame, win

EXE = "Icarus/Binaries/Win64/IcarusServer-Win64-Shipping.exe"
_CFG = "Saved/Config/WindowsServer"

class IcarusGame(WineGame):
    kind = "icarus"
    label = "Icarus"
    steam_app = 2089300
    exe = EXE
    run_dir = "Icarus/Binaries/Win64"
    install_gb = 10
    ram_note = "about 8-12 GB of memory"
    about = "Session-based survival on an alien planet, up to 8 players. Runs through Wine."
    # no graceful shutdown under Wine — the game saves the mission as it goes
    port_layout = [
        {"name": "game", "klass": "game", "start": 17777, "proto": "UDP", "forward": True,
         "label": "Game port (UDP)", "help": "The port players connect to. Forward it (UDP)."},
        {"name": "query", "klass": "query", "start": 27095, "proto": "UDP", "forward": True,
         "label": "Steam query port (UDP)", "help": "Lists the server in the browser. Forward it (UDP)."},
    ]
    extra_fields = [
        {"name": "maxplayers", "label": "Max players (1-8)", "type": "number", "min": 1, "max": 8,
         "default": 8},
        {"name": "anyone_launch", "label": "Any player may start a mission (off = admins only)",
         "type": "checkbox", "default": True},
        {"name": "anyone_delete", "label": "Any player may delete a mission's save",
         "type": "checkbox", "default": False},
    ]
    provision_hint = ("Icarus — a new server with its own save folder (a Windows server, run through "
                      "Wine). The join password is the shared one. After joining, type "
                      "/AdminLogin followed by the shared admin password in chat to manage it. The "
                      "first player to join picks the mission (“prospect”) or open world to play.")

    def command(self, spec, ports, name, server_dir, install):
        self.option(spec, "maxplayers")
        return (f'wine ./IcarusServer-Win64-Shipping.exe -Log -UserDir="{win(server_dir)}\\\\" \\\n'
                f'    -SteamServerName="{name}" -PORT={ports["game"]} -QueryPort={ports["query"]}')

    def write_files(self, spec, ports, name, server_dir, install):
        b = lambda field, default: "True" if opt_bool(spec, field, default) else "False"  # noqa: E731
        ini = ("[/Script/Icarus.DedicatedServerSettings]\n"
               f"SessionName={name}\n"
               "JoinPassword=set-at-launch\n"
               f"MaxPlayers={self.option(spec, "maxplayers")}\n"
               "AdminPassword=set-at-launch\n"
               # by default the server quits when nobody has joined or everyone has left
               "ShutdownIfNotJoinedFor=-1.000000\n"
               "ShutdownIfEmptyFor=-1.000000\n"
               f"AllowNonAdminsToLaunchProspects={b('anyone_launch', True)}\n"
               f"AllowNonAdminsToDeleteProspects={b('anyone_delete', False)}\n"
               "ResumeProspect=True\n")
        os.makedirs(os.path.join(server_dir, _CFG), exist_ok=True)
        common.write_private(self._ini(server_dir), ini)

    def sync_lines(self, spec, ports, name, server_dir, install):
        return common.password_sync(self._ini(server_dir), [("JoinPassword", "join"), ("AdminPassword", "admin")])

    @staticmethod
    def _ini(server_dir):
        return os.path.join(server_dir, _CFG, "ServerSettings.ini")

    def save_dir(self, server_dir, install):
        return os.path.join(server_dir, "Saved")

    def log_file(self, server_dir, install):
        return os.path.join(server_dir, "Saved/Logs/Icarus.log")
