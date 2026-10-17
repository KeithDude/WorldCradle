"""Conan Exiles game type. The dedicated server runs under Wine (Windows build).

Each server keeps its settings, database and logs in its own folder (the
server's -userdir option). Setting names are keys of the game's ini files.
Players and messages go through the game's RCON console.
"""
from __future__ import annotations

import os
import re

import monitor
from games import common
from games.base import empty_probe
from games.simple import RCON_PORT_HELP
from games.winegames import WineGame, win

EXE = "ConanSandbox/Binaries/Win64/ConanSandboxServer-Win64-Shipping.exe"
_CFG = "Saved/Config/WindowsServer"   # inside the server's own folder (-userdir)

class ConanGame(WineGame):
    kind = "conan"
    label = "Conan Exiles"
    steam_app = 443030
    exe = EXE
    run_dir = "ConanSandbox/Binaries/Win64"
    install_gb = 5
    ram_note = "about 6-10 GB of memory"
    about = "Open-world survival in the world of Conan. Runs through Wine."
    rcon_commands = {"broadcast": 'broadcast "{message}"'}
    rcon_lenient = True          # its RCON replies don't follow the protocol strictly
    # no graceful shutdown under Wine — the game saves to its database continuously
    port_layout = [
        {"name": "game", "klass": "game", "start": 7790, "span": 2, "proto": "UDP", "forward": True,
         "label": "Game port (UDP)", "help": "The game also uses the next port up. Forward both (UDP)."},
        {"name": "query", "klass": "query", "start": 27080, "proto": "UDP", "forward": True,
         "label": "Steam query port (UDP)", "help": "Lists the server in the browser. Forward it (UDP)."},
        {"name": "rcon", "klass": "rcon", "start": 25620, "proto": "TCP", "label": "Admin console port (TCP)",
         "help": RCON_PORT_HELP},
    ]
    extra_fields = [
        {"name": "maxplayers", "label": "Max players (1-70)", "type": "number", "min": 1, "max": 70,
         "default": 10},
        {"name": "mode", "label": "Combat", "type": "select", "default": "pve",
         "options": [["pve", "PvE (players vs the world)"], ["pvp", "PvP (players can fight and raid)"]]},
    ]
    provision_hint = ("Conan Exiles — a new world in its own folder (run through Wine). The join password "
                      "is the shared one; the shared admin password unlocks the in-game admin panel. "
                      "Rates and rules start at the game's defaults and can be changed in-game as admin. "
                      "Its first start takes a few minutes.")

    def command(self, spec, ports, name, server_dir, install):
        return (f'wine ./ConanSandboxServer-Win64-Shipping.exe -log -userdir="{win(server_dir)}\\\\" \\\n'
                f'    -Port={ports["game"]} -QueryPort={ports["query"]} -MaxPlayers={self.option(spec, "maxplayers")} \\\n'
                f'    -ServerName="{name}" -ServerPassword="$GAME_SERVER_PASSWORD"')

    def write_files(self, spec, ports, name, server_dir, install):
        pvp = self.option(spec, "mode") == "pvp"
        cfg_dir = os.path.join(server_dir, _CFG)
        os.makedirs(cfg_dir, exist_ok=True)
        # the server adds every other setting, with its default, on first start
        for file, body in (
            ("ServerSettings.ini", f"[ServerSettings]\nPVPEnabled={'True' if pvp else 'False'}\n"
                                   "AdminPassword=set-at-launch\n"),
            ("Game.ini", f"[RconPlugin]\nRconEnabled=1\nRconPort={ports['rcon']}\n"
                         "RconPassword=set-at-launch\nRconMaxKarma=60\n"),
        ):
            common.write_private(os.path.join(cfg_dir, file), body)

    def sync_lines(self, spec, ports, name, server_dir, install):
        return (common.password_sync(os.path.join(server_dir, _CFG, "ServerSettings.ini"), [("AdminPassword", "admin")])
                + common.password_sync(os.path.join(server_dir, _CFG, "Game.ini"), [("RconPassword", "admin")]))

    def save_dir(self, server_dir, install):
        return os.path.join(server_dir, "Saved")

    def log_file(self, server_dir, install):
        return os.path.join(server_dir, "Saved/Logs/ConanSandbox.log")

    @staticmethod
    def parse_players(text: str) -> list[str] | None:
        # header row, then "  0 | CharName | PlayerName | UserID | PlatformID | PlatformName"
        if "Idx" not in (text or ""):
            return None
        names = []
        for line in text.splitlines()[1:]:
            cols = [c.strip() for c in line.split("|")]
            if len(cols) >= 3 and cols[0].isdigit():
                names.append(cols[1] or cols[2])
        return names

    def probe(self, s) -> dict:
        out = empty_probe()
        info = monitor.a2s_info(s.query_port) if s.query_port else None
        if info is not None:
            out.update(reachable=True, players=info["players"], max_players=info["max_players"])
        names = self.parse_players(self.rcon_send(s, "listplayers") or "") \
            if s.rcon_port else None
        if names is not None:
            out.update(reachable=True, players=len(names), player_names=names,
                       player_detail=[{"name": n, "id": ""} for n in names])
        return out

    def broadcast(self, s, message: str) -> str:
        return super().broadcast(s, re.sub(r'"', " ", message))
