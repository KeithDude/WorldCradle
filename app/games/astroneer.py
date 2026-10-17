"""Astroneer — a Windows-only server run through Wine, built on games/winegames.py (WineGame)."""
from __future__ import annotations

import os

from games import common
from games.base import ActionError, empty_probe, safe_name
from games.simple import GAME_PORT_HELP, RCON_PORT_HELP, port
from games.winegames import WineGame, win


def _astro_console(port: int, password: str, command: str, wait: float = 1.5) -> str | None:
    """One command on an Astroneer server's console (plain text over TCP; the
    password is the first line). The answer, "" if there was none, None if the
    console couldn't be reached."""
    import socket
    import time
    try:
        with socket.create_connection(("127.0.0.1", int(port)), timeout=5) as s:
            s.sendall(password.encode() + b"\n")
            time.sleep(0.3)
            s.sendall(command.encode() + b"\n")
            s.settimeout(wait)
            data = b""
            try:
                while not data.endswith(b"\n"):
                    chunk = s.recv(65536)
                    if not chunk:
                        break
                    data += chunk
            except OSError:
                pass
            return data.decode("utf-8", "replace").strip()
    except OSError:
        return None


class AstroneerGame(WineGame):
    kind = "astroneer"
    label = "Astroneer"
    steam_app = 728470
    exe = "Astro/Binaries/Win64/AstroServer-Win64-Shipping.exe"
    run_dir = "Astro/Binaries/Win64"
    install_gb = 3
    ram_note = "about 2-4 GB of memory"
    about = "Relaxed space exploration and base building for up to 8 players. Runs through Wine."
    has_query = False
    actions = {"save"}
    stop_seconds = 45
    port_layout = [port("game", 8777, "Game port (UDP)", help=GAME_PORT_HELP),
                   port("rcon", 8778, "Admin console port (TCP)", proto="TCP", forward=False,
                        help=RCON_PORT_HELP)]
    extra_fields = [
        {"name": "owner", "label": "Owner — your Steam display name (optional)", "placeholder": "",
         "help": "The player with this exact name becomes the server's owner in the game and can "
                 "manage it from the in-game server menu."},
        {"name": "maxplayers", "label": "Max players (1-8)", "type": "number", "min": 1, "max": 8,
         "default": 8},
    ]
    provision_hint = ("Astroneer — a new save in its own folder (a Windows server, run through Wine). "
                      "The join password is the shared one. Friends add the server in the game's "
                      "server list by address: your public address, a colon, then the game port. "
                      "The server tells the game's online service where it is, so it looks up this "
                      "network's public address each time it starts.")

    def _ini(self, server_dir):
        return os.path.join(server_dir, "Saved", "Config", "WindowsServer", "AstroServerSettings.ini")

    def command(self, spec, ports, name, server_dir, install):
        self.option(spec, "maxplayers")
        owner = (spec.get("owner") or "").strip()
        if owner and safe_name(owner, 64) != owner:
            raise ActionError("Owner name: please use plain letters, digits, spaces and common punctuation.")
        return f'wine ./AstroServer-Win64-Shipping.exe -log -userdir="{win(server_dir)}\\\\"'

    def write_files(self, spec, ports, name, server_dir, install):
        # only the settings chosen here; the server adds the rest with its defaults
        cfg = os.path.dirname(self._ini(server_dir))
        os.makedirs(cfg, exist_ok=True)
        ini = ("[/Script/Astro.AstroServerSettings]\r\n"
               "PublicIP=\r\n"
               f"ServerName={name}\r\n"
               f"OwnerName={(spec.get('owner') or '').strip()}\r\n"
               "ServerPassword=set-at-launch\r\n"
               "ConsolePassword=set-at-launch\r\n"
               f"ConsolePort={ports['rcon']}\r\n"
               f"MaximumPlayerCount={self.option(spec, "maxplayers")}\r\n"
               "AutoSaveGameInterval=600\r\n")
        common.write_private(self._ini(server_dir), ini)
        with open(os.path.join(cfg, "Engine.ini"), "w", encoding="utf-8", newline="") as f:
            f.write(f"[URL]\r\nPort={ports['game']}\r\n")

    def sync_lines(self, spec, ports, name, server_dir, install):
        ini = self._ini(server_dir)
        return (common.password_sync(ini, [("ServerPassword", "join"), ("ConsolePassword", "admin")])
                # the game's online service must be told this network's current public address
                + f'python3 - "{ini}" <<\'ADDR\'\n'
                "import re, socket, sys, urllib.request\n"
                'for url in ("https://api.ipify.org", "https://checkip.amazonaws.com", "https://ifconfig.me/ip"):\n'
                "    try:\n"
                '        ip = urllib.request.urlopen(url, timeout=6).read(64).decode("ascii", "replace").strip()\n'
                "        socket.inet_aton(ip)\n"
                "    except Exception:\n"
                "        continue\n"
                '    t = open(sys.argv[1], encoding="utf-8", newline="").read()\n'
                "    t = re.sub(r'(?m)^PublicIP=[^\\r\\n]*', lambda m: 'PublicIP=' + ip, t)\n"
                '    open(sys.argv[1], "w", encoding="utf-8", newline="").write(t)\n'
                "    break\n"
                "ADDR\n")

    def stop_lines(self, spec, ports, name, server_dir, install):
        # the console's shutdown command saves the game and exits
        return (f"python3 - {ports['rcon']} \"$GAME_ADMIN_PASSWORD\" <<'STOP'\n"
                "import socket, sys, time\n"
                "try:\n"
                '    s = socket.create_connection(("127.0.0.1", int(sys.argv[1])), timeout=5)\n'
                '    s.sendall(sys.argv[2].encode() + b"\\n"); time.sleep(0.5)\n'
                '    s.sendall(b"DSServerShutdown\\n"); time.sleep(2); s.close()\n'
                "except OSError:\n"
                "    pass\n"
                "STOP\n")

    def save_dir(self, server_dir, install):
        return os.path.join(server_dir, "Saved")

    def probe(self, s) -> dict:
        import json
        out = empty_probe()
        if not s.rcon_port:
            return out
        try:
            stats = json.loads(_astro_console(s.rcon_port, s.rcon_password, "DSServerStatistics") or "")
            listing = json.loads(_astro_console(s.rcon_port, s.rcon_password, "DSListPlayers") or "{}")
        except (TypeError, ValueError):
            return out
        names = [p.get("playerName") or "?" for p in listing.get("playerInfo") or [] if p.get("inGame")]
        out.update(reachable=True, players=int(stats.get("playersInGame") or 0),
                   max_players=stats.get("maxInGamePlayers"), player_names=names,
                   player_detail=[{"name": n, "id": ""} for n in names])
        return out

    def save(self, s) -> str:
        if _astro_console(s.rcon_port, s.rcon_password, "DSSaveGame", wait=4) is None:
            raise ActionError(f"Save on {s.name} failed (the admin console didn't answer).")
        return "saved"
