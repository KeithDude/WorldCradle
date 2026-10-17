"""Voyagers of Nera — a Windows-only server run through Wine, built on games/winegames.py (WineGame)."""
from __future__ import annotations

import os

from games import common
from games.base import empty_probe
from games.simple import port
from games.winegames import WineGame, win


class NeraGame(WineGame):
    reports_players = False     # it has no way to list who is on
    kind = "nera"
    label = "Voyagers of Nera"
    steam_app = 3937860
    exe = "BoatGame/Binaries/Win64/BoatGameServer-Win64-Shipping.exe"
    run_dir = "BoatGame/Binaries/Win64"
    install_gb = 8
    ram_note = "about 4-8 GB of memory"
    about = "Co-op ocean survival and sailing adventure for up to 10 players. Runs through Wine."
    has_query = False
    port_layout = [port("game", 7777, "Game port (UDP, plus the next one)", span=2,
                        help="The port players connect to. Forward it and the one after it (UDP).")]
    extra_fields = [
        {"name": "maxplayers", "label": "Max players (1-10)", "type": "number", "min": 1, "max": 10,
         "default": 10},
        {"name": "autosave", "label": "Autosave every … seconds (10-900)", "type": "number", "min": 10,
         "max": 900, "default": 300,
         "help": "The game's makers recommend leaving this at 300 (5 minutes)."},
    ]
    provision_hint = ("Voyagers of Nera — a new world in its own folder (a Windows server, run through "
                      "Wine). The join password is the shared one — this game only accepts letters and digits "
                      "in a password, so the shared one must be plain. Friends find the server under "
                      "Browse Dedicated Servers, or use the short join code the server makes each time "
                      "it starts (shown on the server's card). There is "
                      "no “save now” command, so stopping the server can lose up to one autosave "
                      "interval of progress, and the dashboard can't show its player count.")

    def _ini(self, server_dir):
        return os.path.join(server_dir, "Saved", "PersistedData", "nera_dedicatedserver", "CustomConfig",
                            "CustomHostServerUserSettings.ini")

    def command(self, spec, ports, name, server_dir, install):
        self.option(spec, "maxplayers")
        self.option(spec, "autosave")
        return (f'wine ./BoatGameServer-Win64-Shipping.exe -log -port={ports["game"]} '
                f'-userdir="{win(server_dir)}\\\\"')

    def write_files(self, spec, ports, name, server_dir, install):
        os.makedirs(os.path.dirname(self._ini(server_dir)), exist_ok=True)
        common.write_private(self._ini(server_dir), "[/Script/BoatGame.BGCustomHostServerSettings]\r\n"
                # the game documents letters and digits only, 30 at most
                f"HostServerDisplayName={''.join(c for c in name if c.isalnum() or c == ' ')[:30].strip()}\r\n"
                "HostServerPassword=set-at-launch\r\n"
                f"MaxPlayers={self.option(spec, "maxplayers")}\r\n"
                f"AutosaveTimerSeconds={self.option(spec, "autosave")}\r\n")

    def sync_lines(self, spec, ports, name, server_dir, install):
        # forget the last run's join code so the card never shows a stale one
        return (common.password_sync(self._ini(server_dir), [("HostServerPassword", "join")])
                + f'rm -f "{server_dir}/Saved/DedicatedServerMagicJoinCode.txt"\n')

    def save_dir(self, server_dir, install):
        return os.path.join(server_dir, "Saved")

    def log_file(self, server_dir, install):
        return os.path.join(server_dir, "Saved", "Logs", "BoatGame.log")

    def probe(self, s) -> dict:
        import re
        out = empty_probe()
        try:   # <server folder>/Saved/DedicatedServerMagicJoinCode.txt, written once the server is up
            path = os.path.join(os.path.dirname(os.path.dirname(s.log_path)), "DedicatedServerMagicJoinCode.txt")
            with open(path, encoding="utf-8-sig") as f:
                code = f.read(64).strip()
        except OSError:
            return out
        if re.match(r"^[A-Za-z0-9]{4,16}$", code):
            out.update(reachable=True, note=f"Friends join with code: {code}")
        return out
