"""Windrose — a Windows-only server run through Wine, built on games/winegames.py (WineGame)."""
from __future__ import annotations

import os

from games import common
from games.base import empty_probe
from games.simple import port
from games.winegames import WineGame


class WindroseGame(WineGame):
    kind = "windrose"
    label = "Windrose"
    steam_app = 4129620
    exe = "R5/Binaries/Win64/WindroseServer-Win64-Shipping.exe"
    run_dir = "R5/Binaries/Win64"
    needs_install_clone = True   # its settings file and saves sit beside the program files
    install_gb = 3
    ram_note = "about 8 GB of memory for 2 players, 16 GB for 10"
    about = "Co-op pirate survival and sailing adventure. Runs through Wine."
    has_query = False
    port_layout = [port("game", 7777, "Direct-connection port (TCP and UDP)", proto="UDP and TCP",
                        help="Only used with the “direct address” connection: forward it for both TCP and UDP.")]
    CONNECT = [["code", "Invite code — friends type a code; no router setup needed"],
               ["direct", "Direct address — friends type your address and port (needs port forwarding)"]]
    extra_fields = [
        {"name": "connect", "label": "How friends connect", "type": "select", "options": CONNECT,
         "default": "code"},
        {"name": "maxplayers", "label": "Max players (1-10)", "type": "number", "min": 1, "max": 10,
         "default": 4},
    ]
    provision_note = ("Windrose keeps its settings and saves beside its program files, so each server "
                      "gets its own copy of the game (about 3 GB).")
    provision_hint = ("Windrose — a new world with its own copy of the game (a Windows server, run "
                      "through Wine). The join password is the shared one. With the default “invite "
                      "code” connection there is normally nothing to set up on your router (it relies on the "
                      "router's automatic port opening, UPnP, which most home routers have on): the "
                      "server's card shows the code friends type under Play → Connect to Server.")

    @staticmethod
    def _desc(install):
        return os.path.join(install, "R5", "ServerDescription.json")

    def command(self, spec, ports, name, server_dir, install):
        self.option(spec, "connect")
        self.option(spec, "maxplayers")
        # -realmcradle=… means nothing to the game; it lets the dashboard tell this server's process apart
        return f'wine ./WindroseServer-Win64-Shipping.exe -realmcradle={os.path.basename(server_dir)} -log'

    def write_files(self, spec, ports, name, server_dir, install):
        import json
        import secrets
        import string
        direct = self.option(spec, "connect") == "direct"
        code = "".join(secrets.choice(string.ascii_lowercase + string.digits) for _ in range(8))
        desc = {"Version": 1, "ServerDescription_Persistent": {
            "InviteCode": code, "IsPasswordProtected": True, "Password": "set-at-launch",
            "ServerName": name, "MaxPlayerCount": self.option(spec, "maxplayers"),
            "UseDirectConnection": direct, "DirectConnectionServerPort": ports["game"],
            "DirectConnectionProxyAddress": "0.0.0.0", "AutoLoadLatestBackupIfHasBroken": True,
            # each server runs from its own copy, so several may run on one computer
            "CanLaunchMultipleServerInstances": True}}
        common.write_private(self._desc(install), json.dumps(desc, indent="\t"))

    def sync_lines(self, spec, ports, name, server_dir, install):
        return common.json_password_sync(
            self._desc(install), [(("ServerDescription_Persistent", "Password"), "join")],
            extra=('d["ServerDescription_Persistent"]["IsPasswordProtected"] = bool(join)\n'
                   # Under Wine the server picks 127.0.0.1 for its connection sockets, which friends
                   # can't reach; give it this computer's network address.
                   "import socket\n"
                   "try:\n"
                   "    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)\n"
                   '    s.connect(("192.0.2.1", 9))\n'
                   '    d["ServerDescription_Persistent"]["P2pProxyAddress"] = s.getsockname()[0]\n'
                   "except OSError:\n"
                   "    pass"))

    def save_dir(self, server_dir, install):
        return os.path.join(install, "R5", "Saved")

    def log_file(self, server_dir, install):
        return os.path.join(install, "R5", "Saved", "Logs", "R5.log")

    def proc_pattern(self, spec, ports, server_dir):
        return f"-realmcradle={spec['key']} -log"

    def probe(self, s) -> dict:
        import json
        out = empty_probe()
        try:
            with open(self._desc(s.install_dir), encoding="utf-8-sig") as f:
                d = json.load(f)["ServerDescription_Persistent"]
        except (OSError, ValueError, KeyError, TypeError):
            return out
        out["max_players"] = d.get("MaxPlayerCount")
        if d.get("UseDirectConnection"):
            import monitor
            out["reachable"] = monitor.port_listening(s.game_port) or None
        elif d.get("InviteCode"):
            out["note"] = f"Friends join with invite code: {d['InviteCode']}"
        return out
