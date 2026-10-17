"""Eco — a native Linux server, built on games/simple.py (SimpleGame)."""
from __future__ import annotations

import os
import re

from games import common
from games.base import ActionError, empty_probe, safe_name
from games.simple import GAME_PORT_HELP, RCON_PORT_HELP, SimpleGame, port


class EcoGame(SimpleGame):
    kind = "eco"
    label = "Eco"
    steam_app = 739590
    exe = "EcoServer"
    needs_install_clone = True   # settings and the world live beside the program files
    requires_libs = ["gdiplus"]  # its map renderer loads libgdiplus; without it the server exits at start
    install_gb = 0.6
    ram_note = "about 4-8 GB of memory; creating a new world takes several minutes"
    about = "Build a civilisation together without wrecking the planet's ecosystem."
    has_query = False
    kill_signal = "SIGTERM"      # the documented safe shutdown: saves the world, then exits
    stop_seconds = 90
    port_layout = [port("game", 3000, "Game port (UDP)", help=GAME_PORT_HELP),
                   port("web", 3001, "Web page port (TCP)", proto="TCP",
                        help="The server's own web page (map, graphs, laws). Forward it (TCP) if friends should see it."),
                   port("rcon", 3002, "Admin console port (TCP)", proto="TCP", forward=False,
                        help=RCON_PORT_HELP),
                   port("steam", 3003, "Steam port", form=False, forward=False, klass="query")]
    extra_fields = [
        {"name": "maxplayers", "label": "Max players (blank = no limit)", "type": "number", "min": 1,
         "max": 500, "placeholder": "no limit"},
        {"name": "description", "label": "Description — optional", "placeholder": ""},
        {"name": "user_token", "label": "Eco server token — recommended", "placeholder": "",
         "help": "Sign in at play.eco, open your account page and create a server token. With it the "
                 "server verifies players' Eco accounts. Without it the server runs in offline mode: "
                 "fine for trusted friends, but it can't confirm who anyone is."},
    ]
    provision_note = ("Eco keeps its world and settings beside its program files, so each server gets its "
                      "own copy of the game (about half a GB).")
    provision_hint = ("Eco — a new world with its own copy of the game. The join password is the shared "
                      "one. The server isn't listed publicly (that needs a token from your Eco account in "
                      "its Network settings); friends connect by address. World size, meteor and "
                      "difficulty settings are in the server's Configs folder.")

    def command(self, spec, ports, name, server_dir, install):
        self.option(spec, "maxplayers")
        token = (spec.get("user_token") or "").strip()
        if token and not re.match(r"^[A-Za-z0-9._\-]{20,2000}$", token):
            raise ActionError("That doesn't look like an Eco server token — copy it again from your "
                              "Eco account page.")
        # The server must either sign in to the game's online service with the
        # owner's token, or run offline (it then can't verify who players are).
        return "./EcoServer -nogui " + (f'-userToken="{token}"' if token else "-offline")

    def write_files(self, spec, ports, name, server_dir, install):
        import json
        net = json.load(open(os.path.join(install, "Configs", "Network.eco.template"), encoding="utf-8-sig"))
        net.update({
            "PublicServer": False, "Name": name, "Password": "set-at-launch",
            "DetailedDescription": safe_name(spec.get("description") or "", 200),
            "GameServerPort": ports["game"], "WebServerPort": ports["web"],
            "RconServerPort": ports["rcon"], "SteamServerPort": ports["steam"],
            "RconPassword": "set-at-launch", "UPnPEnabled": False,
            "RconIPAddress": "127.0.0.1",     # the admin console listens on this computer only
            "DefaultSlots": self.option(spec, "maxplayers") or -1,
        })
        common.write_private(os.path.join(install, "Configs", "Network.eco"), json.dumps(net, indent=2))

    def pre(self, spec, ports, name, server_dir, install):
        return common.json_password_sync(os.path.join(install, "Configs", "Network.eco"),
                                         [(("Password",), "join"), (("RconPassword",), "admin")])

    def save_dir(self, server_dir, install):
        return os.path.join(install, "Storage")

    def proc_pattern(self, spec, ports, server_dir):
        return os.path.dirname(os.path.dirname(server_dir)) + "/EcoServer"

    def probe(self, s) -> dict:
        import json
        import urllib.request
        out = empty_probe()
        web = (s.port_map or {}).get("web") if getattr(s, "port_map", None) else None
        web = web or next(iter(getattr(s, "extra_ports", []) or []), None)
        if not web:
            return out
        try:   # the server's own status page
            with urllib.request.urlopen(f"http://127.0.0.1:{int(web)}/info", timeout=4) as r:
                info = json.load(r)
            names = list(info.get("OnlinePlayersNames") or [])
            out.update(reachable=True, players=int(info.get("OnlinePlayers") or 0), player_names=names,
                       player_detail=[{"name": n, "id": ""} for n in names])
        except Exception:
            pass
        return out
