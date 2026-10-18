"""Unturned game type (native Linux dedicated server).

Each server is a folder under the install's Servers/ directory; its settings
are lines in Servers/<id>/Server/Commands.dat, which the server runs at start.
Admin commands go to the server's console; player numbers come from the Steam
query port.
"""
from __future__ import annotations

import os
import re

import monitor
from games import common
from games.base import ActionError, empty_probe, safe_name
from games.simple import SimpleGame

LAUNCHER = "ServerHelper.sh"
MAPS = [["PEI", "PEI"], ["Washington", "Washington"], ["Russia", "Russia"], ["Germany", "Germany"],
        ["Yukon", "Yukon"]]
MODES = [["Easy", "Easy"], ["Normal", "Normal"], ["Hard", "Hard"]]
PERSPECTIVES = [["Both", "First and third person"], ["First", "First person only"],
                ["Third", "Third person only"]]
_TOKEN_RE = re.compile(r"^[A-Fa-f0-9]{32}$")

def _server_id(key: str) -> str:
    return "wc_" + key.replace("-", "_")


class UnturnedGame(SimpleGame):
    kind = "unturned"
    label = "Unturned"
    steam_app = 1110390
    exe = LAUNCHER
    query_on_game_port = True
    console_commands = {"save": "save", "broadcast": "say {message}", "kick": "kick {target}",
                        "ban": "ban {target}"}
    quit_command = "shutdown"    # saves, then quits
    install_gb = 2
    ram_note = "about 2-4 GB of memory"
    about = "Blocky zombie survival. Free to play, so easy for friends to join."
    port_layout = [
        {"name": "game", "klass": "game", "start": 27200, "span": 2, "proto": "UDP", "forward": True,
         "label": "Game port (UDP)", "help": "The game also uses the next port up. Forward both (UDP)."},
    ]
    extra_fields = [
        {"name": "map", "label": "Map", "type": "select", "options": MAPS, "default": "PEI"},
        {"name": "mode", "label": "Difficulty", "type": "select", "options": MODES, "default": "Normal"},
        {"name": "pvp", "label": "Combat", "type": "select", "default": "PVE",
         "options": [["PVE", "Players vs zombies only (PvE)"], ["PVP", "Players can fight each other (PvP)"]]},
        {"name": "perspective", "label": "Camera", "type": "select", "options": PERSPECTIVES,
         "default": "Both"},
        {"name": "maxplayers", "label": "Max players (1-48)", "type": "number", "min": 1, "max": 48,
         "default": 12},
        {"name": "welcome", "label": "Welcome message — optional", "placeholder": ""},
        {"name": "gslt", "label": "Steam game-server token — needed to appear in the public server list",
         "placeholder": "32 letters and digits",
         "help": "Free from steamcommunity.com/dev/managegameservers (sign in, App ID 304930, create). "
                 "Without one the server isn't listed, but friends can still join with the Server Code "
                 "it prints in its log when it starts, or through a Steam friend invite."},
    ]
    provision_hint = ("Unturned — a new world in its own folder. The join password is the shared one. "
                      "To be listed publicly the game requires a free Steam game-server token (see the tip "
                      "on that box). Without one, friends join with the Server Code shown in the "
                      "server's log. ⚠ Unturned has no autosave: the world is saved when the server "
                      "is stopped from here or when you press Save.")

    def server_folder(self, install, key):
        return os.path.join(install, "Servers", _server_id(key))

    def command(self, spec, ports, name, server_dir, install):
        token = (spec.get("gslt") or "").strip()
        if token and not _TOKEN_RE.match(token):
            raise ActionError("The Steam game-server token should be 32 letters and digits.")
        nettype = "InternetServer" if token else "LanServer"
        return f"./{LAUNCHER} +{nettype}/{os.path.basename(server_dir)}"

    def write_files(self, spec, ports, name, server_dir, install):
        lines = [
            f"Name {name}",
            f"Port {ports['game']}",
            "Password set-at-launch",
            f"MaxPlayers {self.option(spec, "maxplayers")}",
            f"Map {self.option(spec, "map")}",
            f"Mode {self.option(spec, "mode")}",
            self.option(spec, "pvp"),
            f"Perspective {self.option(spec, "perspective")}",
        ]
        welcome = safe_name(spec.get("welcome") or "", 120)
        if welcome:
            lines.append(f"Welcome {welcome}")
        token = (spec.get("gslt") or "").strip()
        if token:
            lines.append(f"GSLT {token}")
        os.makedirs(os.path.join(server_dir, "Server"), exist_ok=True)
        common.write_private(self._commands(server_dir), "\n".join(lines) + "\n")   # holds the password + token

    def pre(self, spec, ports, name, server_dir, install):
        return common.password_sync(self._commands(server_dir), [("Password", "join")], sep=" ")

    @staticmethod
    def _commands(server_dir):
        return os.path.join(server_dir, "Server", "Commands.dat")

    def proc_pattern(self, spec, ports, server_dir):
        return f"Server/{_server_id(spec['key'])}"     # its "+LanServer/<id>" (or InternetServer) argument

    def probe(self, s) -> dict:
        out = empty_probe()
        info = monitor.a2s_info(s.query_port) if s.query_port else None
        if info is not None:
            names = monitor.a2s_player_names(s.query_port) if info["players"] else []
            out.update(reachable=True, players=info["players"], max_players=info["max_players"],
                       player_names=names, player_detail=[{"name": n, "id": n} for n in names])
        return out

    def valid_target(self, target: str) -> bool:
        return bool(re.match(r"^[^\r\n/\x00-\x1f]{1,64}$", target))
