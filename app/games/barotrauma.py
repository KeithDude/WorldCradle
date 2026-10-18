"""Barotrauma — a native Linux server, built on games/simple.py.

The server keeps its settings next to its own program files, so each server
gets its own copy of the (small) install. Name, ports, limit and password are
launch arguments. Who is online is read from the server's output.
"""
from __future__ import annotations

import os
import re

import monitor
from games.base import empty_probe
from games.simple import SimpleGame, port

EXE = "DedicatedServer"
_EVENTS = re.compile(r"^\s*(?P<joined>[^\r\n]{1,40}?) has joined the server\.\s*$|^\s*(?P<left>[^\r\n]{1,40}?) has left the server\.\s*$", re.M)

class BarotraumaGame(SimpleGame):
    kind = "barotrauma"
    label = "Barotrauma"
    steam_app = 1026340
    exe = EXE
    install_gb = 0.4
    ram_note = "about 1-2 GB of memory"
    about = "Co-op submarine survival in an alien ocean. Light on resources."
    has_query = False
    reports_answering = False   # who's on comes from its output, not a port check
    kill_signal = "SIGTERM"
    stop_seconds = 30
    needs_install_clone = True
    port_layout = [
        port("game", 27600, "Game port (UDP)", help="The port players connect to. Forward it (UDP)."),
        port("query", 27601, "Steam query port (UDP)", help="Used when the server is listed publicly. Forward it (UDP)."),
    ]
    extra_fields = [
        {"name": "maxplayers", "label": "Max players (1-16)", "type": "number", "min": 1, "max": 16,
         "default": 8},
        {"name": "public", "label": "List in the public server browser", "type": "checkbox",
         "default": False},
    ]
    provision_note = ("Barotrauma keeps its settings beside its program files, so each server gets its "
                      "own copy of the game (under half a GB). Campaign saves are different: the game "
                      "keeps them in one folder for the whole computer, so if you run several Barotrauma "
                      "servers, a backup or restore of one covers all of their campaigns.")
    provision_hint = ("Barotrauma — a new server with its own copy of the game. The join password is the "
                      "shared one. Round settings (submarine, mission, difficulty) are chosen in the "
                      "game's lobby by whoever has permission.")

    def command(self, spec, ports, name, server_dir, install):
        return (f'./{EXE} -name "{name}" -port {ports["game"]} -queryport {ports["query"]} '
                f'-maxplayers {self.option(spec, "maxplayers")} \\\n'
                f'    -public {"true" if self.option(spec, "public") else "false"} -password "$GAME_SERVER_PASSWORD" '
                f'> "{self.log_file(server_dir, install)}" 2>&1 < /dev/null')

    def log_file(self, server_dir, install):
        return os.path.join(install, "worldcradle-console.log")

    def save_dir(self, server_dir, install):
        # The game saves every campaign here, whichever server played it; WorldCradle doesn't yet
        # give each server its own folder (owners are told in provision_note; on the roadmap).
        return os.path.expanduser("~/.local/share/Daedalic Entertainment GmbH/Barotrauma/Multiplayer")

    def proc_pattern(self, spec, ports, server_dir):
        return f"-port {ports['game']} -queryport"

    def probe(self, s) -> dict:
        out = empty_probe()
        names = monitor.roster_from_log(s.log_path, _EVENTS) if s.log_path else None
        if names is not None:
            out.update(players=len(names), player_names=names,
                       player_detail=[{"name": n, "id": ""} for n in names])
        return out
