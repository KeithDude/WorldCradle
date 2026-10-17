"""VEIN — a native Linux server, built on games/simple.py (SimpleGame)."""
from __future__ import annotations

import os
import re

from games import common
from games.base import ActionError, safe_name
from games.simple import GAME_PORT_HELP, QUERY_PORT_HELP, SimpleGame, port


class VeinGame(SimpleGame):
    kind = "vein"
    label = "VEIN"
    steam_app = 2131400
    exe = "Vein/Binaries/Linux/VeinServer-Linux-Test"
    install_gb = 10
    ram_note = "about 6-10 GB of memory"
    about = "Post-apocalyptic survival sandbox with deep scavenging and crafting."
    kill_signal = "SIGTERM"
    port_layout = [port("game", 7790, "Game port (UDP)", help=GAME_PORT_HELP),
                   port("query", 27200, "Steam query port (UDP)", help=QUERY_PORT_HELP)]
    extra_fields = [
        {"name": "maxplayers", "label": "Max players (1-64)", "type": "number", "min": 1, "max": 64,
         "default": 8},
        {"name": "description", "label": "Description shown in the server list — optional", "placeholder": ""},
        {"name": "public", "label": "List in the public server browser", "type": "checkbox", "default": True},
        {"name": "admins", "label": "Admins — Steam IDs (the long numbers), comma-separated; optional",
         "placeholder": "7656119..."},
    ]
    provision_hint = ("VEIN — a new world in its own folder. The join password is the shared one. To be "
                      "an admin in-game, put your Steam ID (the long number) in the Admins box.")

    def _cfg(self, server_dir):
        return os.path.join(server_dir, "Saved", "Config", "LinuxServer", "Game.ini")

    def command(self, spec, ports, name, server_dir, install):
        self.option(spec, "maxplayers")
        ids = [a.strip() for a in (spec.get("admins") or "").split(",") if a.strip()]
        if any(not re.match(r"^\d{17}$", a) for a in ids):
            raise ActionError("Admin Steam IDs are 17-digit numbers (find yours at steamid.io).")
        return (f'./Vein/Binaries/Linux/VeinServer-Linux-Test Vein -log -userdir="{server_dir}" '
                f'-Port={ports["game"]} -QueryPort={ports["query"]}')

    def write_files(self, spec, ports, name, server_dir, install):
        ids = [a.strip() for a in (spec.get("admins") or "").split(",") if a.strip()]
        ini = ("[/Script/Engine.GameSession]\n"
               f"MaxPlayers={self.option(spec, "maxplayers")}\n\n"
               "[/Script/Vein.VeinGameSession]\n"
               f"bPublic={'True' if self.option(spec, "public") else 'False'}\n"
               f'ServerName={name}\n'
               f'ServerDescription={safe_name(spec.get("description") or "", 200)}\n'
               "BindAddr=0.0.0.0\n"
               # more than one entry: every one after the first needs a leading "+"
               + "".join(f"{'+' if n else ''}SuperAdminSteamIDs={i}\n" for n, i in enumerate(ids)) +
               'Password=set-at-launch\n\n'
               "[OnlineSubsystemSteam]\n"
               f"GameServerQueryPort={ports['query']}\n")
        os.makedirs(os.path.dirname(self._cfg(server_dir)), exist_ok=True)
        common.write_private(self._cfg(server_dir), ini)

    def pre(self, spec, ports, name, server_dir, install):
        cfg = self._cfg(server_dir)
        # The server rewrites Game.ini and may drop lines, so put the password back if it is
        # gone. It also needs Steam's library beside its program (a documented first-run step).
        return (common.password_sync(cfg, [("Password", "join")], section="[/Script/Vein.VeinGameSession]")
                + f'for lib in "$HOME/.steam/sdk64/steamclient.so" "$HOME/.local/share/Steam/steamcmd/linux64/steamclient.so" '
                f'"$HOME/.steam/steam/steamcmd/linux64/steamclient.so" "{install}/linux64/steamclient.so"; do\n'
                f'    [ -e "{install}/Vein/Binaries/Linux/steamclient.so" ] && break\n'
                f'    [ -e "$lib" ] && ln -s "$lib" "{install}/Vein/Binaries/Linux/steamclient.so"\n'
                "done\n")

    def save_dir(self, server_dir, install):
        return os.path.join(server_dir, "Saved")

    def log_file(self, server_dir, install):
        return os.path.join(server_dir, "Saved", "Logs", "Vein.log")
