"""RuneScape: Dragonwilds — a native Linux server, built on games/simple.py (SimpleGame)."""
from __future__ import annotations

import os
import re

from games import common
from games.base import ActionError, safe_name
from games.simple import GAME_PORT_HELP, SimpleGame, port


class DragonwildsGame(SimpleGame):
    kind = "dragonwilds"
    label = "RuneScape: Dragonwilds"
    steam_app = 4019830
    exe = "RSDragonwilds/Binaries/Linux/RSDragonwildsServer-Linux-Shipping"
    install_gb = 6
    ram_note = "about 2 GB of memory plus 1 GB per player (up to 6 players)"
    about = "Co-op survival crafting in the RuneScape universe, for up to 6 players."
    has_query = False
    kill_signal = "SIGTERM"
    port_layout = [port("game", 7790, "Game port (UDP)", help=GAME_PORT_HELP)]
    POLICIES = [["Crossplay", "Everyone (crossplay)"], ["SteamOnly", "Steam players only"]]
    extra_fields = [
        {"name": "owner_id", "label": "Your Player ID (required)", "placeholder": "long code from the game's settings",
         "help": "The server must know who owns it. In Dragonwilds open Settings and copy your Player ID "
                 "from the bottom of the screen; that player becomes the server's owner and admin."},
        {"name": "world", "label": "World name", "placeholder": "My World"},
    ]
    provision_hint = ("RuneScape: Dragonwilds — a new world in its own folder. The world password is the "
                      "shared join password. The server will not start without your Player ID (see the "
                      "tip on that box). Friends find it on the Public tab of the game's Worlds screen by "
                      "searching for the exact world name (capital letters matter). The player whose "
                      "ID you entered is the server's owner and manages it from inside the game.")

    def _cfg(self, server_dir):
        return os.path.join(server_dir, "Saved", "Config", "LinuxServer", "DedicatedServer.ini")

    def _owner(self, spec):
        owner = (spec.get("owner_id") or "").strip()
        if not re.match(r"^[A-Za-z0-9_\-]{8,64}$", owner):
            raise ActionError("Paste your Player ID — in Dragonwilds open Settings and copy it from the "
                              "bottom of the screen. The server can't run without an owner.")
        return owner

    def command(self, spec, ports, name, server_dir, install):
        self._owner(spec)
        return (f'./RSDragonwilds/Binaries/Linux/RSDragonwildsServer-Linux-Shipping RSDragonwilds -log '
                f'-userdir="{server_dir}" -Port={ports["game"]}')

    def write_files(self, spec, ports, name, server_dir, install):
        world = safe_name(spec.get("world") or "", 40) or name
        ini = ("[/Script/Dominion.DedicatedServerSettings]\n"
               f"OwnerId={self._owner(spec)}\n"
               f"ServerName={name}\n"
               "WorldPassword=set-at-launch\n"
               f"DefaultWorldName={world}\n"
               "PlatformPolicy=Crossplay\n"
               "bAllowSendingCrashDumps=False\n")
        os.makedirs(os.path.dirname(self._cfg(server_dir)), exist_ok=True)
        common.write_private(self._cfg(server_dir), ini)

    def pre(self, spec, ports, name, server_dir, install):
        cfg = self._cfg(server_dir)
        # the server rewrites this file, so add a password line back if it has gone missing
        return common.password_sync(cfg, [("WorldPassword", "join")],
                                    section="[/Script/Dominion.DedicatedServerSettings]")

    def save_dir(self, server_dir, install):
        return os.path.join(server_dir, "Saved")

    def log_file(self, server_dir, install):
        return os.path.join(server_dir, "Saved", "Logs", "RSDragonwilds.log")
