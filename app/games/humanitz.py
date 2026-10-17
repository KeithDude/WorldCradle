"""HumanitZ — a native Linux server, built on games/simple.py (SimpleGame)."""
from __future__ import annotations

import os
import re

from games import common
from games.base import empty_probe, opt_bool
from games.simple import GAME_PORT_HELP, QUERY_PORT_HELP, RCON_PORT_HELP, SimpleGame, port


class HumanitzGame(SimpleGame):
    kind = "humanitz"
    label = "HumanitZ"
    steam_app = 2728330
    steam_beta = "linuxbranch"   # the Linux server is published on this Steam branch
    exe = "HumanitZServer/Binaries/Linux/HumanitZServer-Linux-Shipping"
    needs_install_clone = True   # its settings file sits beside the program files
    install_gb = 1.5
    ram_note = "about 4-8 GB of memory"
    about = "Top-down zombie survival with vehicles and base building."
    # no "save" console command is documented; the game autosaves
    rcon_commands = {"broadcast": "admin {message}"}
    rcon_lenient = True          # its RCON is only "similar to" Valve's
    stop_seconds = 120           # the makers' own service example allows it up to 5 minutes to save and exit
    port_layout = [port("game", 7790, "Game port (UDP)", help=GAME_PORT_HELP),
                   port("query", 27180, "Steam query port (UDP)", help=QUERY_PORT_HELP),
                   port("rcon", 8890, "Admin console port (TCP)", proto="TCP", forward=False,
                        help=RCON_PORT_HELP)]
    extra_fields = [
        {"name": "maxplayers", "label": "Max players (1-32)", "type": "number", "min": 1, "max": 32,
         "default": 8},
        {"name": "pvp", "label": "Players can hurt each other (PvP)", "type": "checkbox", "default": False},
        {"name": "permadeath", "label": "Permadeath (a dead character is gone)", "type": "checkbox",
         "default": False},
        {"name": "loot_respawn", "label": "Loot respawns over time", "type": "checkbox", "default": True},
    ]
    provision_note = ("HumanitZ keeps its settings beside its program files, so each server gets its own "
                      "copy of the game (about 1.5 GB).")
    provision_hint = ("HumanitZ — a new world with its own copy of the game. The join and admin passwords "
                      "are the shared ones (in-game: /AdminAccess and the admin password). The many "
                      "zombie, loot and rarity settings are in the server's GameServerSettings.ini.")

    def _ini(self, install):
        return os.path.join(install, "HumanitZServer", "GameServerSettings.ini")

    def command(self, spec, ports, name, server_dir, install):
        self.option(spec, "maxplayers")
        return (f'./HumanitZServer/Binaries/Linux/HumanitZServer-Linux-Shipping HumanitZServer -log '
                f'-port={ports["game"]} -queryport={ports["query"]} -steamservername="{name}"')

    def write_files(self, spec, ports, name, server_dir, install):
        ref = open(os.path.join(install, "HumanitZServer", "REF_GameServerSettings.ini"),
                   encoding="utf-8-sig").read()
        b = lambda field, default: "true" if opt_bool(spec, field, default) else "false"  # noqa: E731
        for key, value in (
            ("ServerName", f'"{name}"'), ("Password", '"set-at-launch"'), ("AdminPass", '"set-at-launch"'),
            ("MaxPlayers", self.option(spec, "maxplayers")),
            ("RCONEnabled", "true"), ("RConPort", ports["rcon"]), ("RCONPass", '"set-at-launch"'),
            ("PVP", b("pvp", False)), ("PermaDeath", b("permadeath", False)),
            ("LootRespawn", b("loot_respawn", True)),
        ):
            ref = common.ini_set(ref, key, value)
        common.write_private(self._ini(install), ref)

    def pre(self, spec, ports, name, server_dir, install):
        return common.password_sync(self._ini(install),
                                    [("Password", "join"), ("AdminPass", "admin"), ("RCONPass", "admin")], quoted=True)

    def save_dir(self, server_dir, install):
        return os.path.join(install, "HumanitZServer", "Saved")

    def proc_pattern(self, spec, ports, server_dir):
        return f"-port={ports['game']} -queryport"

    has_query = False   # it doesn't answer Steam's query; the admin console lists players instead

    @staticmethod
    def parse_players(text: str) -> list[str] | None:
        if text is None:
            return None
        if "No players connected" in text:
            return []
        names = []
        for line in text.splitlines():
            line = line.strip()
            if line and line != "None":
                names.append(re.split(r"\s*[(\[|]", line, maxsplit=1)[0].strip() or line)
        return names

    def probe(self, s) -> dict:
        out = empty_probe()
        names = self.parse_players(self.rcon_send(s, "Players")) if s.rcon_port else None
        if names is not None:
            out.update(reachable=True, players=len(names), player_names=names,
                       player_detail=[{"name": n, "id": ""} for n in names])
        return out

