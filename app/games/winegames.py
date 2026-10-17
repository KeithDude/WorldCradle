"""winegames.py — Windows-only dedicated servers of the "one program plus launch
arguments" kind, run through Wine.

Builds on games/simple.py: each server gets its own Wine environment (see
common.wine_prefix) and its own data folder, handed to the game as a Windows
path. Wine can't pass a "please save and quit" signal on to these servers, so
stopping one ends it at once (unless the game has a console that can shut it
down, like Astroneer); they all save on their own as they run.
"""
from __future__ import annotations

import os

from games import common
from games.base import ActionError, empty_probe, safe_name
from games.simple import GAME_PORT_HELP, RCON_PORT_HELP, SimpleGame, port


def win(path: str) -> str:
    """A Linux path as the Windows path Wine shows it at, written for use inside
    double quotes in a launch script."""
    return "Z:" + path.replace("/", "\\\\")


class WineGame(SimpleGame):
    steam_platform = "windows"
    requires = ["wine"]
    stop_seconds = 30

    def sync_lines(self, spec, ports, name, server_dir, install) -> str:
        """Shell lines run before each start (password syncing and the like)."""
        return ""

    def pre(self, spec, ports, name, server_dir, install):
        key = os.path.basename(server_dir)
        return (self.sync_lines(spec, ports, name, server_dir, install)
                + common.wine_env_lines(common.wine_prefix(self.kind, key)))

    def proc_pattern(self, key, ports, server_dir):
        return f"gamedash-servers\\\\{key}\\\\"


class ScumGame(WineGame):
    kind = "scum"
    label = "SCUM"
    steam_app = 3792580
    exe = "SCUM/Binaries/Win64/SCUMServer.exe"
    run_dir = "SCUM/Binaries/Win64"
    install_gb = 15
    ram_note = "about 10-16 GB of memory"
    about = "Hardcore open-world prison-island survival. Runs through Wine; slow to start."
    has_query = False
    port_layout = [port("game", 7042, "Game port (UDP, plus the next two)", span=3,
                        help="The port players connect to. Forward it and the two after it (UDP).")]
    extra_fields = [
        {"name": "maxplayers", "label": "Max players (1-64)", "type": "number", "min": 1, "max": 64,
         "default": 16},
        {"name": "mode", "label": "Play style", "type": "select", "default": "PVE",
         "options": [["PVE", "PvE (players vs the world)"], ["PVP", "PvP"]]},
        {"name": "welcome", "label": "Welcome message — optional", "placeholder": ""},
    ]
    provision_hint = ("SCUM — a new world in its own folder (a Windows server, run through Wine). The "
                      "join password is the shared one. ⚠ Every start is slow: about 20 minutes the "
                      "first time and 10 after that, during which the card shows it as running but "
                      "nobody can join yet. BattlEye anti-cheat is off because it can't run under Wine. "
                      "Admins are the Steam IDs listed in the server's AdminUsers.ini; the dashboard "
                      "can't show its player count. If a friend adds the server by address and the "
                      "game port doesn't work, have them try the game port plus 2 — the community "
                      "guide says that is the port to type.")

    def _ini(self, server_dir):
        return os.path.join(server_dir, "Saved", "Config", "WindowsServer", "ServerSettings.ini")

    def command(self, spec, ports, name, server_dir, install):
        maxp = self.option(spec, "maxplayers")
        self.option(spec, "mode")
        # -noheartbeatthread: under Wine the long map load trips the engine's "hang" watchdog, which kills it
        return (f'wine ./SCUMServer.exe -log -port={ports["game"]} -MaxPlayers={maxp} -nobattleye '
                f'-noheartbeatthread -userdir="{win(server_dir)}\\\\"')

    def write_files(self, spec, ports, name, server_dir, install):
        # The server throws away a settings file that doesn't list every setting,
        # so start from its complete default file (games/data) and change ours.
        import re
        src = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "scum_ServerSettings.ini")
        text = open(src, encoding="utf-8", newline="").read()
        for key, value in (
            ("scum.ServerName", name), ("scum.ServerPassword", "set-at-launch"),
            ("scum.MaxPlayers", self.option(spec, "maxplayers")),
            ("scum.ServerPlaystyle", self.option(spec, "mode")),
            ("scum.WelcomeMessage", safe_name(spec.get("welcome") or "", 200) or "Welcome!"),
        ):
            text, n = re.subn(r"(?m)^%s=[^\r\n]*" % re.escape(key), lambda m: f"{key}={value}", text)
            if n != 1:
                raise ActionError(f"SCUM's settings template is missing {key}.")
        os.makedirs(os.path.dirname(self._ini(server_dir)), exist_ok=True)
        common.write_private(self._ini(server_dir), text)

    def sync_lines(self, spec, ports, name, server_dir, install):
        return common.password_sync(self._ini(server_dir), [("scum.ServerPassword", "join")])

    def save_dir(self, server_dir, install):
        return os.path.join(server_dir, "Saved")

    def log_file(self, server_dir, install):
        return os.path.join(server_dir, "Saved", "Logs", "SCUM.log")


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
        # -gamedash=… means nothing to the game; it lets the dashboard tell this server's process apart
        return f'wine ./WindroseServer-Win64-Shipping.exe -log -gamedash={os.path.basename(server_dir)}'

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

    def proc_pattern(self, key, ports, server_dir):
        return f"-gamedash={key}$"

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


class StarRuptureGame(WineGame):
    kind = "starrupture"
    label = "StarRupture"
    steam_app = 3809400
    exe = "StarRupture/Binaries/Win64/StarRuptureServerEOS-Win64-Shipping.exe"
    run_dir = ""                 # it looks for DSSettings.txt in the folder it is started from
    needs_install_clone = True   # its session settings and passwords are files beside the program
    install_gb = 20
    ram_note = "about 8-16 GB of memory"
    about = "Co-op base building and survival on a hostile planet (early access). Runs through Wine."
    has_query = False
    port_layout = [port("game", 7777, "Game port (UDP)",
                        help="The port players connect to. Forward it for UDP only — never TCP.")]
    extra_fields = [
        {"name": "autosave", "label": "Autosave every … seconds (60-3600)", "type": "number", "min": 60,
         "max": 3600, "default": 300},
    ]
    provision_note = ("StarRupture keeps its session settings beside its program files, so each server "
                      "gets its own copy of the game (about 20 GB).")
    provision_hint = ("StarRupture — a new session with its own copy of the game (a Windows server, run "
                      "through Wine). The session starts by itself; friends join by this network's "
                      "public address and the game port. ⚠ The shared join password is NOT applied: "
                      "this game stores its passwords in an encrypted form only the game itself can "
                      "write, so the server is open to anyone who has the address. The game's in-game "
                      "“Manage Server” screen is switched off on purpose — it lets anyone on the "
                      "internet take the server over. The dashboard can't show its player count.")

    @staticmethod
    def _session(server_dir):
        return ("gd" + "".join(c for c in os.path.basename(server_dir) if c.isalnum()))[:20]

    def command(self, spec, ports, name, server_dir, install):
        self.option(spec, "autosave")
        # The two RCWeb switches turn off the engine's remote-control web interface, which
        # otherwise answers on the game port with no login at all.
        # -gamedash=… means nothing to the game; it lets the dashboard tell this server's process apart.
        return ('wine ./StarRupture/Binaries/Win64/StarRuptureServerEOS-Win64-Shipping.exe -Log '
                f'-Port={ports["game"]} -RCWebControlDisable -RCWebInterfaceDisable '
                f'-gamedash={os.path.basename(server_dir)}')

    def sync_lines(self, spec, ports, name, server_dir, install):
        # DSSettings.txt tells the server which session to run. "Start a new game" must only be
        # set while there is no save yet: left on, it would overwrite the save at every start.
        session = self._session(server_dir)
        interval = self.option(spec, "autosave")
        return (f'python3 - "{install}" "{session}" "{interval}" <<\'SESSION\'\n'
                "import glob, json, os, sys\n"
                "root, session, interval = sys.argv[1:4]\n"
                'saves = sorted(glob.glob(os.path.join(root, "StarRupture", "Saved", "SaveGames", "**", "*.sav"),\n'
                "                         recursive=True), key=os.path.getmtime)\n"
                "d = {\"SessionName\": session, \"SaveGameInterval\": interval,\n"
                "     \"StartNewGame\": \"false\" if saves else \"true\",\n"
                "     \"LoadSavedGame\": \"true\" if saves else \"false\",\n"
                "     \"SaveGameName\": os.path.basename(saves[-1]) if saves else \"AutoSave0.sav\"}\n"
                'json.dump(d, open(os.path.join(root, "DSSettings.txt"), "w", encoding="utf-8"), indent=2)\n'
                "SESSION\n")

    def save_dir(self, server_dir, install):
        return os.path.join(install, "StarRupture", "Saved")

    def log_file(self, server_dir, install):
        return os.path.join(install, "StarRupture", "Saved", "Logs", "StarRupture.log")

    def proc_pattern(self, key, ports, server_dir):
        return f"-gamedash={key}$"
