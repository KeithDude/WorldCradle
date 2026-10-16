"""More native-Linux Steam servers built on games/simple.py — one class each."""
from __future__ import annotations

import os
import re

import monitor
from games.base import ActionError, opt_bool, opt_choice, opt_int, safe_name
from games.simple import GAME_PORT_HELP, QUERY_PORT_HELP, RCON_PORT_HELP, SimpleGame, port

_TOKEN_RE = re.compile(r"^[A-Fa-f0-9]{32}$")


def _gslt_field(app_id: int) -> dict:
    return {"name": "gslt", "label": "Steam game-server token — optional, needed for the public server list",
            "placeholder": "32 letters and digits",
            "help": f"Free from steamcommunity.com/dev/managegameservers (sign in, App ID {app_id}, create)."}


def _gslt(spec: dict) -> str:
    token = (spec.get("gslt") or "").strip()
    if token and not _TOKEN_RE.match(token):
        raise ActionError("The Steam game-server token should be 32 letters and digits.")
    return token


class InsurgencyGame(SimpleGame):
    kind = "insurgency"
    label = "Insurgency: Sandstorm"
    steam_app = 581330
    kill_signal = "SIGTERM"   # it crashes on Ctrl-C; there is no world to save
    exe = "Insurgency/Binaries/Linux/InsurgencyServer-Linux-Shipping"
    run_dir = "Insurgency/Binaries/Linux"
    install_gb = 5
    ram_note = "about 2-4 GB of memory"
    about = "Tactical team shooter with co-op and versus modes."
    actions = {"broadcast"}
    port_layout = [port("game", 27102, "Game port (UDP)", help=GAME_PORT_HELP),
                   port("query", 27131, "Steam query port (UDP)", help=QUERY_PORT_HELP),
                   port("rcon", 27140, "Admin console port (TCP)", proto="TCP", forward=False,
                        help=RCON_PORT_HELP)]
    SCENARIOS = {
        "coop_hideout": ("Co-op Checkpoint — Hideout", "Town", "Scenario_Hideout_Checkpoint_Security"),
        "coop_farmhouse": ("Co-op Checkpoint — Farmhouse", "Farmhouse", "Scenario_Farmhouse_Checkpoint_Security"),
        "push_refinery": ("Push — Refinery", "Oilfield", "Scenario_Refinery_Push_Security"),
        "firefight_crossing": ("Firefight — Crossing", "Canyon", "Scenario_Crossing_Firefight_West"),
    }
    provision_hint = ("Insurgency: Sandstorm — everything is set when the server starts; there is no saved "
                      "world. The join and admin passwords are the shared ones.")

    @property
    def extra_fields(self) -> list[dict]:
        return [{"name": "scenario", "label": "Starting mode and map", "type": "select",
                 "default": "coop_hideout", "options": [[k, v[0]] for k, v in self.SCENARIOS.items()]},
                {"name": "maxplayers", "label": "Max players (1-28)", "type": "number", "min": 1,
                 "max": 28, "default": 8},
                _gslt_field(581320)]

    def command(self, spec, ports, name, server_dir, install):
        _, mapname, scenario = self.SCENARIOS[opt_choice(spec, "scenario", list(self.SCENARIOS),
                                                         "coop_hideout", "Starting mode and map")]
        maxp = opt_int(spec, "maxplayers", 8, 1, 28, "Max players")
        token = _gslt(spec)
        return (f'./InsurgencyServer-Linux-Shipping "{mapname}?Scenario={scenario}?MaxPlayers={maxp}'
                f'?Password=$GAME_SERVER_PASSWORD" -Port={ports["game"]} -QueryPort={ports["query"]} '
                f'-hostname="{name}" -Rcon -RconPassword="$GAME_ADMIN_PASSWORD" '
                f'-RconListenPort={ports["rcon"]} -log'
                + (f" -GSLTToken={token}" if token else ""))

    def proc_pattern(self, key, ports, server_dir):
        return f"-Port={ports['game']} -QueryPort"

    def broadcast(self, s, message: str) -> str:
        r = monitor.rcon_run(s.rcon_port, s.rcon_password, "say " + message.replace("\n", " ")[:200])
        if r is None:
            raise ActionError(f"Message to {s.name} failed (the admin console didn't answer).")
        return "sent"


class Kf2Game(SimpleGame):
    kind = "kf2"
    label = "Killing Floor 2"
    steam_app = 232130
    exe = "Binaries/Win64/KFGameSteamServer.bin.x86_64"
    install_gb = 25
    ram_note = "about 2-3 GB of memory"
    about = "Co-op wave shooter against monsters, up to 6 players."
    port_layout = [port("game", 7790, "Game port (UDP)", help=GAME_PORT_HELP),
                   port("query", 27170, "Steam query port (UDP)", help=QUERY_PORT_HELP),
                   port("web", 8090, "Web admin port (TCP)", proto="TCP", forward=False, klass="rcon",
                        form=False)]
    MAPS = ["KF-BioticsLab", "KF-BurningParis", "KF-Outpost", "KF-VolterManor", "KF-Catacombs",
            "KF-EvacuationPoint", "KF-Farmhouse", "KF-BlackForest", "KF-ContainmentStation", "KF-Prison"]
    DIFFICULTIES = [["0", "Normal"], ["1", "Hard"], ["2", "Suicidal"], ["3", "Hell on Earth"]]
    LENGTHS = [["0", "Short (4 waves)"], ["1", "Medium (7 waves)"], ["2", "Long (10 waves)"]]
    provision_hint = ("Killing Floor 2 — everything is set when the server starts; there is no saved "
                      "world. The join and admin passwords are the shared ones.")

    @property
    def extra_fields(self) -> list[dict]:
        return [{"name": "map", "label": "Starting map", "type": "select", "default": "KF-BioticsLab",
                 "options": [[m, m[3:]] for m in self.MAPS]},
                {"name": "difficulty", "label": "Difficulty", "type": "select", "default": "0",
                 "options": self.DIFFICULTIES},
                {"name": "length", "label": "Game length", "type": "select", "default": "1",
                 "options": self.LENGTHS}]   # the game is always 6 players

    def command(self, spec, ports, name, server_dir, install):
        key = re.sub(r"[^A-Za-z0-9_]", "_", spec["key"])
        mapname = opt_choice(spec, "map", self.MAPS, "KF-BioticsLab", "Starting map")
        diff = opt_choice(spec, "difficulty", [d for d, _ in self.DIFFICULTIES], "0", "Difficulty")
        length = opt_choice(spec, "length", [d for d, _ in self.LENGTHS], "1", "Game length")
        # ConfigSubDir gives this server its own settings folder under KFGame/Config
        return (f'./Binaries/Win64/KFGameSteamServer.bin.x86_64 "{mapname}?ConfigSubDir=gd_{key}'
                f'?Difficulty={diff}?GameLength={length}'
                f'?GamePassword=$GAME_SERVER_PASSWORD?AdminPassword=$GAME_ADMIN_PASSWORD" '
                f'-Port={ports["game"]} -QueryPort={ports["query"]} -WebAdminPort={ports["web"]} '
                f'-ServerName="\\"{name}\\""')

    def proc_pattern(self, key, ports, server_dir):
        return f"-Port={ports['game']} -QueryPort"


def json_password_sync(path: str, edits: str) -> str:
    """Shell lines that load a JSON settings file as `d`, apply `edits` (Python
    using `join` and `admin`, the two shared passwords) and write it back."""
    return (f'python3 - "{path}" "$GAME_SERVER_PASSWORD" "$GAME_ADMIN_PASSWORD" <<\'SYNC\'\n'
            "import json, sys\n"
            "p, join, admin = sys.argv[1:4]\n"
            'd = json.load(open(p, encoding="utf-8"))\n'
            f"{edits}\n"
            'json.dump(d, open(p, "w", encoding="utf-8"), indent=2)\n'
            "SYNC\n")


class ArmaReforgerGame(SimpleGame):
    kind = "armareforger"
    label = "Arma Reforger"
    steam_app = 1874900
    exe = "ArmaReforgerServer"
    install_gb = 9
    ram_note = "about 4-8 GB of memory"
    about = "Military sandbox with large-scale Conflict battles and a Game Master mode."
    kill_signal = "SIGTERM"
    port_layout = [port("game", 2001, "Game port (UDP)", help=GAME_PORT_HELP),
                   port("query", 17777, "Steam query port (UDP)", help=QUERY_PORT_HELP)]
    SCENARIOS = [["{ECC61978EDCC2B5A}Missions/23_Campaign.conf", "Conflict — Everon"],
                 ["{59AD59368755F41A}Missions/21_GM_Eden.conf", "Game Master — Everon"]]
    extra_fields = [
        {"name": "scenario", "label": "Scenario", "type": "select", "options": SCENARIOS,
         "default": SCENARIOS[0][0]},
        {"name": "maxplayers", "label": "Max players (1-128)", "type": "number", "min": 1, "max": 128,
         "default": 16},
        {"name": "visible", "label": "List in the public server browser", "type": "checkbox", "default": True},
        {"name": "battleye", "label": "BattlEye anti-cheat", "type": "checkbox", "default": True},
        {"name": "crossplay", "label": "Allow Xbox players (crossplay)", "type": "checkbox", "default": True},
    ]
    provision_hint = ("Arma Reforger — a new server with its own settings and profile folder. The join and "
                      "admin passwords are the shared ones (log in as admin in-game with #login and the "
                      "admin password).")

    def command(self, spec, ports, name, server_dir, install):
        opt_choice(spec, "scenario", [s for s, _ in self.SCENARIOS], self.SCENARIOS[0][0], "Scenario")
        opt_int(spec, "maxplayers", 16, 1, 128, "Max players")
        return (f'./ArmaReforgerServer -config "{server_dir}/config.json" -profile "{server_dir}/profile" '
                f"-maxFPS 60 -nothrow")

    def write_files(self, spec, ports, name, server_dir, install):
        import json
        cfg = {
            "bindAddress": "0.0.0.0", "bindPort": ports["game"], "publicPort": ports["game"],
            "a2s": {"address": "0.0.0.0", "port": ports["query"]},
            "game": {
                "name": name, "password": "set-at-launch", "passwordAdmin": "set-at-launch",
                "scenarioId": opt_choice(spec, "scenario", [s for s, _ in self.SCENARIOS],
                                         self.SCENARIOS[0][0], "Scenario"),
                "maxPlayers": opt_int(spec, "maxplayers", 16, 1, 128, "Max players"),
                "visible": opt_bool(spec, "visible", True),
                "crossPlatform": opt_bool(spec, "crossplay", True),
                "gameProperties": {"battlEye": opt_bool(spec, "battleye", True)},
            },
        }
        fd = os.open(os.path.join(server_dir, "config.json"), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
        os.makedirs(os.path.join(server_dir, "profile"), exist_ok=True)

    def pre(self, spec, ports, name, server_dir, install):
        return json_password_sync(os.path.join(server_dir, "config.json"),
                                  'd["game"]["password"] = join\nd["game"]["passwordAdmin"] = admin')

    def save_dir(self, server_dir, install):
        return os.path.join(server_dir, "profile")


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
        opt_int(spec, "maxplayers", None, 1, 500, "Max players")
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
            "DefaultSlots": opt_int(spec, "maxplayers", None, 1, 500, "Max players") or -1,
        })
        fd = os.open(os.path.join(install, "Configs", "Network.eco"), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(net, f, indent=2)

    def pre(self, spec, ports, name, server_dir, install):
        return json_password_sync(os.path.join(install, "Configs", "Network.eco"),
                                  'd["Password"] = join\nd["RconPassword"] = admin')

    def save_dir(self, server_dir, install):
        return os.path.join(install, "Storage")

    def proc_pattern(self, key, ports, server_dir):
        return os.path.dirname(os.path.dirname(server_dir)) + "/EcoServer"

    def probe(self, s) -> dict:
        import json
        import urllib.request
        out = {"players": None, "player_names": [], "player_detail": [],
               "max_players": None, "reachable": None}
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


def ini_set(text: str, key: str, value) -> str:
    """Replace `key=...` in an ini-style text (first match), keeping everything else."""
    pat = re.compile(r"(?m)^%s=.*$" % re.escape(key))
    line = f"{key}={value}"
    return pat.sub(lambda m: line, text, count=1) if pat.search(text) else text + line + "\n"


def ini_password_sync(path: str, pairs: list[tuple[str, str]]) -> str:
    """Shell lines that rewrite `Key="value"` entries of an ini file from the
    shared passwords. `pairs` = [(key, "join" | "admin")]."""
    body = "".join(f'    ("{k}", {which}),\n' for k, which in pairs)
    return (f'python3 - "{path}" "$GAME_SERVER_PASSWORD" "$GAME_ADMIN_PASSWORD" <<\'SYNC\'\n'
            "import re, sys\n"
            "p, join, admin = sys.argv[1:4]\n"
            't = open(p, encoding="utf-8").read()\n'
            "for key, val in (\n" + body + "):\n"
            '    t = re.sub(r\'(?m)^%s=.*$\' % key, lambda m: \'%s="%s"\' % (key, val), t)\n'
            'open(p, "w", encoding="utf-8").write(t)\n'
            "SYNC\n")


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
    actions = {"broadcast"}      # no "save" console command is documented; the game autosaves
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
        opt_int(spec, "maxplayers", 8, 1, 32, "Max players")
        return (f'./HumanitZServer/Binaries/Linux/HumanitZServer-Linux-Shipping HumanitZServer -log '
                f'-port={ports["game"]} -queryport={ports["query"]} -steamservername="{name}"')

    def write_files(self, spec, ports, name, server_dir, install):
        ref = open(os.path.join(install, "HumanitZServer", "REF_GameServerSettings.ini"),
                   encoding="utf-8-sig").read()
        b = lambda field, default: "true" if opt_bool(spec, field, default) else "false"  # noqa: E731
        for key, value in (
            ("ServerName", f'"{name}"'), ("Password", '"set-at-launch"'), ("AdminPass", '"set-at-launch"'),
            ("MaxPlayers", opt_int(spec, "maxplayers", 8, 1, 32, "Max players")),
            ("RCONEnabled", "true"), ("RConPort", ports["rcon"]), ("RCONPass", '"set-at-launch"'),
            ("PVP", b("pvp", False)), ("PermaDeath", b("permadeath", False)),
            ("LootRespawn", b("loot_respawn", True)),
        ):
            ref = ini_set(ref, key, value)
        fd = os.open(self._ini(install), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(ref)

    def pre(self, spec, ports, name, server_dir, install):
        return ini_password_sync(self._ini(install),
                                 [("Password", "join"), ("AdminPass", "admin"), ("RCONPass", "admin")])

    def save_dir(self, server_dir, install):
        return os.path.join(install, "HumanitZServer", "Saved")

    def proc_pattern(self, key, ports, server_dir):
        return f"-port={ports['game']} -queryport"

    def _rcon(self, s, cmd: str, what: str) -> str:
        r = monitor.palworld_rcon(s.rcon_port, s.rcon_password, cmd)   # "similar to" Valve's RCON: tolerant client
        if r is None:
            raise ActionError(f"{what} on {s.name} failed (the admin console didn't answer).")
        return r.strip() or "ok"

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
        out = {"players": None, "player_names": [], "player_detail": [],
               "max_players": None, "reachable": None}
        names = self.parse_players(monitor.palworld_rcon(s.rcon_port, s.rcon_password, "Players")) \
            if s.rcon_port else None
        if names is not None:
            out.update(reachable=True, players=len(names), player_names=names,
                       player_detail=[{"name": n, "id": ""} for n in names])
        return out

    def broadcast(self, s, message: str) -> str:
        self._rcon(s, "admin " + message.replace("\n", " ")[:200], "Message")
        return "sent"


def telnet_lines(port_var: int, lines: list[str]) -> str:
    """Shell lines that type `lines` into a plain-text local console port."""
    payload = "".join(l + "\\r\\n" for l in lines)
    return (f"python3 - {port_var} <<'STOP'\n"
            "import socket, sys, time\n"
            "try:\n"
            '    s = socket.create_connection(("127.0.0.1", int(sys.argv[1])), timeout=5)\n'
            f'    time.sleep(0.5); s.sendall(b"{payload}"); time.sleep(1.5); s.close()\n'
            "except OSError:\n"
            "    pass\n"
            "STOP\n")


class SoulmaskGame(SimpleGame):
    kind = "soulmask"
    label = "Soulmask"
    steam_app = 3017300
    exe = "WS/Binaries/Linux/WSServer-Linux-Shipping"
    needs_install_clone = True   # the world is saved beside the program files
    install_gb = 2.5
    ram_note = "about 8-16 GB of memory"
    about = "Tribal survival and base building with recruitable followers."
    stop_seconds = 260   # saving and closing its database takes a few minutes
    port_layout = [port("game", 8777, "Game port (UDP)", help=GAME_PORT_HELP),
                   port("query", 27190, "Steam query port (UDP)", help=QUERY_PORT_HELP),
                   port("echo", 18888, "Local console port (TCP)", proto="TCP", forward=False, klass="rcon",
                        form=False),
                   port("rcon", 19000, "Admin console port (TCP)", proto="TCP", forward=False, form=False)]
    extra_fields = [
        {"name": "maxplayers", "label": "Max players (1-70)", "type": "number", "min": 1, "max": 70,
         "default": 10},
        {"name": "mode", "label": "Combat", "type": "select", "default": "pve",
         "options": [["pve", "PvE (players vs the world)"], ["pvp", "PvP"]]},
    ]
    provision_note = ("Soulmask saves its world beside its program files, so each server gets its own "
                      "copy of the game (about 2 GB).")
    provision_hint = ("Soulmask — a new world with its own copy of the game. The join and admin passwords "
                      "are the shared ones. The first start takes several minutes while the world loads.")

    def pre(self, spec, ports, name, server_dir, install):
        return f'export LD_LIBRARY_PATH="{install}/linux64:$LD_LIBRARY_PATH"\n'

    def command(self, spec, ports, name, server_dir, install):
        maxp = opt_int(spec, "maxplayers", 10, 1, 70, "Max players")
        mode = opt_choice(spec, "mode", ["pve", "pvp"], "pve", "Combat")
        return (f'./WS/Binaries/Linux/WSServer-Linux-Shipping WS Level01_Main -server -log -UTF8Output '
                f'-MULTIHOME=0.0.0.0 -forcepassthrough -Port={ports["game"]} -QueryPort={ports["query"]} '
                f'-EchoPort={ports["echo"]} -SteamServerName="{name}" -MaxPlayers={maxp} -{mode} '
                f'-PSW="$GAME_SERVER_PASSWORD" -adminpsw="$GAME_ADMIN_PASSWORD" -saving=600 -backup=900 '
                # its remote console otherwise opens on a fixed port on every network address
                f'-rconaddr=127.0.0.1 -rconport={ports["rcon"]} -rconpsw="$GAME_ADMIN_PASSWORD"')

    def stop_lines(self, spec, ports, name, server_dir, install):
        return telnet_lines(ports["echo"], ["saveworld 1", "quit 3"])   # save now, then quit in 3 s

    def save_dir(self, server_dir, install):
        return os.path.join(install, "WS", "Saved")

    def proc_pattern(self, key, ports, server_dir):
        return f"-Port={ports['game']} -QueryPort"


class VeinGame(SimpleGame):
    kind = "vein"
    label = "VEIN"
    steam_app = 2131400
    exe = "Vein/Binaries/Linux/VeinServer-Linux-Test"
    install_gb = 10
    ram_note = "about 6-10 GB of memory"
    about = "Post-apocalyptic survival sandbox with deep scavenging and crafting."
    kill_signal = "SIGTERM"
    port_layout = [port("game", 7790, "Game port (UDP)", help=GAME_PORT_HELP),
                   port("query", 27200, "Steam query port (UDP)", help=QUERY_PORT_HELP)]
    extra_fields = [
        {"name": "maxplayers", "label": "Max players (1-64)", "type": "number", "min": 1, "max": 64,
         "default": 8},
        {"name": "description", "label": "Description shown in the server list — optional", "placeholder": ""},
        {"name": "public", "label": "List in the public server browser", "type": "checkbox", "default": True},
        {"name": "admins", "label": "Admins — Steam IDs (the long numbers), comma-separated; optional",
         "placeholder": "7656119..."},
    ]
    provision_hint = ("VEIN — a new world in its own folder. The join password is the shared one. To be "
                      "an admin in-game, put your Steam ID (the long number) in the Admins box.")

    def _cfg(self, server_dir):
        return os.path.join(server_dir, "Saved", "Config", "LinuxServer", "Game.ini")

    def command(self, spec, ports, name, server_dir, install):
        opt_int(spec, "maxplayers", 8, 1, 64, "Max players")
        ids = [a.strip() for a in (spec.get("admins") or "").split(",") if a.strip()]
        if any(not re.match(r"^\d{17}$", a) for a in ids):
            raise ActionError("Admin Steam IDs are 17-digit numbers (find yours at steamid.io).")
        return (f'./Vein/Binaries/Linux/VeinServer-Linux-Test Vein -log -userdir="{server_dir}" '
                f'-Port={ports["game"]} -QueryPort={ports["query"]}')

    def write_files(self, spec, ports, name, server_dir, install):
        ids = [a.strip() for a in (spec.get("admins") or "").split(",") if a.strip()]
        ini = ("[/Script/Engine.GameSession]\n"
               f"MaxPlayers={opt_int(spec, 'maxplayers', 8, 1, 64, 'Max players')}\n\n"
               "[/Script/Vein.VeinGameSession]\n"
               f"bPublic={'True' if opt_bool(spec, 'public', True) else 'False'}\n"
               f'ServerName={name}\n'
               f'ServerDescription={safe_name(spec.get("description") or "", 200)}\n'
               "BindAddr=0.0.0.0\n"
               # more than one entry: every one after the first needs a leading "+"
               + "".join(f"{'+' if n else ''}SuperAdminSteamIDs={i}\n" for n, i in enumerate(ids)) +
               'Password=set-at-launch\n\n'
               "[OnlineSubsystemSteam]\n"
               f"GameServerQueryPort={ports['query']}\n")
        os.makedirs(os.path.dirname(self._cfg(server_dir)), exist_ok=True)
        fd = os.open(self._cfg(server_dir), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(ini)

    def pre(self, spec, ports, name, server_dir, install):
        cfg = self._cfg(server_dir)
        # The server rewrites Game.ini and may drop lines, so put the password back if it is
        # gone. It also needs Steam's library beside its program (a documented first-run step).
        return (f'python3 - "{cfg}" "$GAME_SERVER_PASSWORD" <<\'SYNC\'\n'
                "import re, sys\n"
                "p, join = sys.argv[1:3]\n"
                't = open(p, encoding="utf-8").read()\n'
                'line = "Password=" + join\n'
                "if re.search(r'(?m)^Password=', t):\n"
                "    t = re.sub(r'(?m)^Password=.*$', lambda m: line, t, count=1)\n"
                "else:\n"
                '    head = "[/Script/Vein.VeinGameSession]"\n'
                '    t = t.replace(head, head + "\\n" + line, 1) if head in t else t + "\\n" + head + "\\n" + line + "\\n"\n'
                'open(p, "w", encoding="utf-8").write(t)\n'
                "SYNC\n"
                f'for lib in "$HOME/.steam/sdk64/steamclient.so" "$HOME/.local/share/Steam/steamcmd/linux64/steamclient.so" '
                f'"$HOME/.steam/steam/steamcmd/linux64/steamclient.so" "{install}/linux64/steamclient.so"; do\n'
                f'    [ -e "{install}/Vein/Binaries/Linux/steamclient.so" ] && break\n'
                f'    [ -e "$lib" ] && ln -s "$lib" "{install}/Vein/Binaries/Linux/steamclient.so"\n'
                "done\n")

    def save_dir(self, server_dir, install):
        return os.path.join(server_dir, "Saved")

    def log_file(self, server_dir, install):
        return os.path.join(server_dir, "Saved", "Logs", "Vein.log")


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
        fd = os.open(self._cfg(server_dir), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(ini)

    def pre(self, spec, ports, name, server_dir, install):
        cfg = self._cfg(server_dir)
        # the server rewrites this file, so add a password line back if it has gone missing
        return (f'python3 - "{cfg}" "$GAME_SERVER_PASSWORD" "$GAME_ADMIN_PASSWORD" <<\'SYNC\'\n'
                "import re, sys\n"
                't = open(sys.argv[1], encoding="utf-8").read()\n'
                'for key, val in (("WorldPassword", sys.argv[2]),):\n'
                '    line = key + "=" + val\n'
                "    if re.search(r'(?m)^%s=' % key, t):\n"
                "        t = re.sub(r'(?m)^%s=.*$' % key, lambda m: line, t, count=1)\n"
                "    else:\n"
                "        t = re.sub(r'(?m)^(\\[/Script/Dominion\\.DedicatedServerSettings\\])$', lambda m: m.group(1) + '\\n' + line, t, count=1)\n"
                'open(sys.argv[1], "w", encoding="utf-8").write(t)\n'
                "SYNC\n")

    def save_dir(self, server_dir, install):
        return os.path.join(server_dir, "Saved")

    def log_file(self, server_dir, install):
        return os.path.join(server_dir, "Saved", "Logs", "RSDragonwilds.log")


STATIONEERS_WORLDS = [["Lunar", "The Moon"], ["Mars2", "Mars"], ["Europa3", "Europa"],
                      ["MimasHerschel", "Mimas"], ["Venus", "Venus"], ["Vulcan2", "Vulcan"]]


class StationeersGame(SimpleGame):
    kind = "stationeers"
    label = "Stationeers"
    steam_app = 600760
    exe = "rocketstation_DedicatedServer.x86_64"
    install_gb = 5
    ram_note = "about 3-6 GB of memory; grows with the size of the base"
    about = "Hardcore space-station building and survival with detailed physics and atmospherics."
    has_query = False        # doesn't answer the Steam query, so no player count
    stop_seconds = 45
    port_layout = [port("game", 27510, "Game port (UDP)", help=GAME_PORT_HELP),
                   port("update", 27511, "Update port (UDP)", klass="query",
                        help="The game's second port. Forward it (UDP) alongside the game port.")]
    extra_fields = [
        {"name": "world", "label": "World", "type": "select", "options": STATIONEERS_WORLDS,
         "default": "Lunar"},
        {"name": "maxplayers", "label": "Max players (1-20)", "type": "number", "min": 1, "max": 20,
         "default": 10},
        {"name": "public", "label": "List in the public server browser", "type": "checkbox", "default": True},
        {"name": "autosave", "label": "Autosave every … seconds (60-3600)", "type": "number", "min": 60,
         "max": 3600, "default": 300},
        {"name": "pause_empty", "label": "Pause the world when nobody is online", "type": "checkbox",
         "default": True},
    ]
    provision_hint = ("Stationeers — a new world in its own save. The join password is the shared one. "
                      "The server has no “save now” command, so stopping it can lose up to one "
                      "autosave interval of progress; the dashboard can't show its player count.")

    @staticmethod
    def _save(server_dir):
        return "gd_" + os.path.basename(server_dir).replace("-", "_")

    def command(self, spec, ports, name, server_dir, install):
        world = opt_choice(spec, "world", [w for w, _ in STATIONEERS_WORLDS], "Lunar", "World")
        return (f'./{self.exe} -batchmode -nographics -logFile "{self.log_file(server_dir, install)}" '
                f'-settingspath "{server_dir}/setting.xml" -load {self._save(server_dir)} {world} '
                f'-settings StartLocalHost true LocalIpAddress 0.0.0.0 UPNPEnabled false UseSteamP2P false '
                f'ServerVisible {"true" if opt_bool(spec, "public", True) else "false"} '
                f'GamePort {ports["game"]} UpdatePort {ports["update"]} '
                f'ServerName "{name}" ServerPassword "$GAME_SERVER_PASSWORD" '
                f'ServerMaxPlayers {opt_int(spec, "maxplayers", 10, 1, 20, "Max players")} '
                f'AutoSave true SaveInterval {opt_int(spec, "autosave", 300, 60, 3600, "Autosave interval")} '
                f'AutoPauseServer {"true" if opt_bool(spec, "pause_empty", True) else "false"}')

    def save_dir(self, server_dir, install):
        return os.path.join(install, "saves", self._save(server_dir))

    def log_file(self, server_dir, install):
        return os.path.join(server_dir, "server.log")


def squad_password_lines(rcon_cfg: str, rcon_port: int, set_join: bool) -> str:
    """Shell lines for Squad-engine servers: put the admin password into Rcon.cfg,
    and (optionally) lock the server with the join password once it is up — that
    can only be done through the admin console, not from a settings file."""
    out = (f'python3 - "{rcon_cfg}" "$GAME_ADMIN_PASSWORD" <<\'SYNC\'\n'
           "import re, sys\n"
           't = open(sys.argv[1], encoding="utf-8").read()\n'
           't = re.sub(r"(?m)^Password=.*$", lambda m: "Password=" + sys.argv[2], t)\n'
           'open(sys.argv[1], "w", encoding="utf-8").write(t)\n'
           "SYNC\n")
    if set_join:
        out += (f"python3 - {rcon_port} \"$GAME_ADMIN_PASSWORD\" \"$GAME_SERVER_PASSWORD\" <<'LOCK' &\n"
                "import socket, struct, sys, time\n"
                "port, admin, join = int(sys.argv[1]), sys.argv[2], sys.argv[3]\n"
                "def pkt(i, kind, body):\n"
                '    b = struct.pack("<ii", i, kind) + body.encode() + b"\\0\\0"\n'
                '    return struct.pack("<i", len(b)) + b\n'
                "for _ in range(240):            # the console opens when the first map has loaded\n"
                "    time.sleep(5)\n"
                "    try:\n"
                '        s = socket.create_connection(("127.0.0.1", port), timeout=5)\n'
                "        s.sendall(pkt(1, 3, admin)); time.sleep(1); s.recv(4096)\n"
                '        s.sendall(pkt(2, 2, "AdminSetServerPassword " + join)); time.sleep(1); s.recv(4096)\n'
                "        s.close(); break\n"
                "    except OSError:\n"
                "        pass\n"
                "LOCK\n")
    return out


class SquadGame(SimpleGame):
    kind = "squad"
    label = "Squad"
    steam_app = 403240
    exe = "SquadGame/Binaries/Linux/SquadGameServer"
    project = "SquadGame"
    join_password_in_server_cfg = False     # no join-password setting in its files: it is set over the admin console
    needs_install_clone = True   # its settings folder sits beside the program files
    install_gb = 14
    ram_note = "about 6-10 GB of memory"
    about = "Large-scale 50-vs-50 military shooter built around teamwork and communication."
    kill_signal = "SIGINT"
    stop_seconds = 30            # matches, not worlds: nothing to save
    actions = {"broadcast"}
    port_layout = [port("game", 7787, "Game port (UDP, plus the next one)", span=2,
                        help="The port players connect to. Forward it and the one after it (UDP)."),
                   port("query", 27165, "Steam query port (UDP and TCP, plus the next one)", span=2,
                        proto="UDP and TCP",
                        help="Lists the server in the browser. Forward it and the one after it (UDP and TCP)."),
                   port("beacon", 15000, "Beacon port (UDP and TCP)", proto="UDP and TCP", form=False),
                   port("rcon", 21114, "Admin console port (TCP)", proto="TCP", forward=False,
                        help=RCON_PORT_HELP)]
    extra_fields = [
        {"name": "maxplayers", "label": "Max players (1-100)", "type": "number", "min": 1, "max": 100,
         "default": 40},
        {"name": "public", "label": "List in the public server browser", "type": "checkbox", "default": True},
        {"name": "locked", "label": "Require the shared join password", "type": "checkbox", "default": True},
    ]

    @property
    def provision_note(self) -> str:
        return (f"{self.label} keeps its settings beside its program files, so each server gets its own "
                f"copy of the game (about {self.install_gb} GB).")

    @property
    def provision_hint(self) -> str:
        join = ("so is the join password" if self.join_password_in_server_cfg
                else "the shared join password is applied a minute or two after the first map loads")
        return (f"{self.label} — a match server with its own copy of the game. The admin password is the "
                f"shared one; {join}. Map rotation and admins are the files in its ServerConfig folder.")

    def _cfg(self, install, name):
        return os.path.join(install, self.project, "ServerConfig", name)

    def command(self, spec, ports, name, server_dir, install):
        maxp = opt_int(spec, "maxplayers", 40, 1, 100, "Max players")
        return (f'./{self.exe} {self.project} Port={ports["game"]} QueryPort={ports["query"]} '
                f'beaconport={ports["beacon"]} FIXEDMAXPLAYERS={maxp} RANDOM=NONE -log')

    def write_files(self, spec, ports, name, server_dir, install):
        edits = {
            "Server.cfg": (("ServerName", f'"{name}"'),
                           ("MaxPlayers", opt_int(spec, "maxplayers", 40, 1, 100, "Max players")),
                           ("ShouldAdvertise", "true" if opt_bool(spec, "public", True) else "false")),
            # the admin console listens on this computer only
            "Rcon.cfg": (("IP", "127.0.0.1"), ("Port", ports["rcon"]), ("Password", "set-at-launch")),
        }
        for fname, pairs in edits.items():
            path = self._cfg(install, fname)
            text = open(path, encoding="utf-8-sig").read()
            for key, value in pairs:
                text = ini_set(text, key, value)
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(text)

    def pre(self, spec, ports, name, server_dir, install):
        locked = opt_bool(spec, "locked", True)
        out = squad_password_lines(self._cfg(install, "Rcon.cfg"), ports["rcon"], locked)
        if self.join_password_in_server_cfg:
            # keep Server.cfg's own password line in step too (empty = no password)
            out += (f'python3 - "{self._cfg(install, "Server.cfg")}" "{"$GAME_SERVER_PASSWORD" if locked else ""}" <<\'SYNC\'\n'
                    "import re, sys\n"
                    't = open(sys.argv[1], encoding="utf-8-sig").read()\n'
                    "line = 'ServerPassword=\"%s\"' % sys.argv[2]\n"
                    "if re.search(r'(?m)^ServerPassword=', t):\n"
                    "    t = re.sub(r'(?m)^ServerPassword=.*$', lambda m: line, t, count=1)\n"
                    "else:\n"
                    "    t = re.sub(r'(?m)^(ServerName=.*)$', lambda m: m.group(1) + '\\n' + line, t, count=1)\n"
                    'open(sys.argv[1], "w", encoding="utf-8").write(t)\n'
                    "SYNC\n")
        return out

    def save_dir(self, server_dir, install):
        return os.path.join(install, self.project, "ServerConfig")

    def log_file(self, server_dir, install):
        return os.path.join(install, self.project, "Saved", "Logs", f"{self.project}.log")

    def proc_pattern(self, key, ports, server_dir):
        return f"Port={ports['game']} QueryPort"

    has_query = False   # no Steam query answer; the admin console reports players instead

    @staticmethod
    def parse_players(text: str) -> list[str]:
        """Names from the "Active Players" part of the console's ListPlayers answer."""
        active = text.split("----- Recently Disconnected", 1)[0]
        return [m.group(1).strip() for m in re.finditer(r"(?m)^ID: \d+ \|.*?\| Name: (.*?) \| Team ID:", active)]

    def probe(self, s) -> dict:
        out = {"players": None, "player_names": [], "player_detail": [],
               "max_players": None, "reachable": None}
        text = monitor.palworld_rcon(s.rcon_port, s.rcon_password, "ListPlayers") if s.rcon_port else None
        if text is not None:
            names = self.parse_players(text)
            out.update(reachable=True, players=len(names), player_names=names,
                       player_detail=[{"name": n, "id": ""} for n in names])
            info = monitor.palworld_rcon(s.rcon_port, s.rcon_password, "ShowServerInfo") or ""
            m = re.search(r'"MaxPlayers":(\d+)', info)
            if m:
                out["max_players"] = int(m.group(1))
        return out

    def broadcast(self, s, message: str) -> str:
        r = monitor.palworld_rcon(s.rcon_port, s.rcon_password,
                                  "AdminBroadcast " + message.replace("\n", " ")[:200])
        if r is None:
            raise ActionError(f"Message to {s.name} failed (the admin console didn't answer).")
        return "sent"


class Squad44Game(SquadGame):
    kind = "squad44"
    label = "Squad 44"
    steam_app = 746200
    exe = "PostScriptum/Binaries/Linux/PostScriptumServer"
    project = "PostScriptum"
    install_gb = 35
    about = "World War II 40-vs-40 tactical shooter (formerly Post Scriptum)."
    join_password_in_server_cfg = True      # Server.cfg has ServerPassword= (Squad's does not)
    port_layout = [port("game", 10027, "Game port (UDP, plus the next one)", span=2,
                        help="The port players connect to. Forward it and the one after it (UDP)."),
                   port("query", 10037, "Steam query port (UDP and TCP, plus the next one)", span=2,
                        proto="UDP and TCP",
                        help="Lists the server in the browser. Forward it and the one after it (UDP and TCP)."),
                   port("beacon", 15010, "Beacon port (UDP)", form=False),
                   port("rcon", 21124, "Admin console port (TCP)", proto="TCP", forward=False,
                        help=RCON_PORT_HELP)]
    extra_fields = [
        {"name": "maxplayers", "label": "Max players (1-80)", "type": "number", "min": 1, "max": 80,
         "default": 40},
        {"name": "public", "label": "List in the public server browser", "type": "checkbox", "default": True},
        {"name": "locked", "label": "Require the shared join password", "type": "checkbox", "default": True},
    ]




class ScpslGame(SimpleGame):
    kind = "scpsl"
    label = "SCP: Secret Laboratory"
    steam_app = 996560
    exe = "LocalAdmin"
    shell = "/bin/bash"          # the launch line feeds the console from a file
    install_gb = 0.6
    ram_note = "about 2-4 GB of memory"
    about = "Multiplayer horror game set in a containment facility; rounds of escape and pursuit."
    has_query = False
    kill_signal = "SIGTERM"
    stop_seconds = 30            # rounds, not worlds: nothing to save
    actions = {"broadcast"}
    port_layout = [port("game", 7777, "Game port (UDP)", help=GAME_PORT_HELP)]
    extra_fields = [
        {"name": "maxplayers", "label": "Max players (1-100)", "type": "number", "min": 1, "max": 100,
         "default": 20},
        {"name": "friendly_fire", "label": "Friendly fire", "type": "checkbox", "default": False},
        {"name": "email", "label": "Contact e-mail — the first step towards the public server list",
         "placeholder": "you@example.com",
         "help": "Leave blank for a private server friends join by address. Getting onto the public "
                 "list takes more than this: the game's makers also ask you to verify the server "
                 "(typing !verify in its console and following their steps) and listed servers may "
                 "have at most 60 players. See techwiki.scpslgame.com."},
    ]
    provision_hint = ("SCP: Secret Laboratory — a round-based server with its own settings folder. The "
                      "game has no join password, so the shared one doesn't apply: friends join by "
                      "address. It stays off the public list unless you complete the makers' verification "
                      "steps (a contact e-mail is only the first of them).")

    def _cfg_dir(self, server_dir, ports):
        return os.path.join(server_dir, "SCP Secret Laboratory", "config", str(ports["game"]))

    def _options(self, spec):
        email = (spec.get("email") or "").strip()
        if email and not re.match(r"^[^@\s]{1,64}@[A-Za-z0-9.-]{1,120}\.[A-Za-z]{2,}$", email):
            raise ActionError("That contact e-mail doesn't look right.")
        return (opt_int(spec, "maxplayers", 20, 1, 100, "Max players"),
                opt_bool(spec, "friendly_fire", False), email)

    def command(self, spec, ports, name, server_dir, install):
        self._options(spec)
        return (f'./LocalAdmin {ports["game"]} --acceptEULA --useDefault --noSetCursor '
                f'> "{self.log_file(server_dir, install)}" 2>&1 < <(tail -n0 -F "$CONSOLE")')

    def write_files(self, spec, ports, name, server_dir, install):
        maxp, ff, email = self._options(spec)
        text = open(os.path.join(install, "ConfigTemplates", "config_gameplay.template.txt"),
                    encoding="utf-8-sig").read()
        for key, value in (("server_name", name), ("max_players", maxp),
                           ("friendly_fire", "true" if ff else "false"),
                           ("contact_email", email or "default"),
                           ("forward_ports", "false")):     # don't ask the router to open ports by itself
            text = re.sub(r"(?m)^%s:.*$" % key, lambda m: f"{key}: {value}", text, count=1)
        os.makedirs(self._cfg_dir(server_dir, ports), exist_ok=True)
        with open(os.path.join(self._cfg_dir(server_dir, ports), "config_gameplay.txt"), "w",
                  encoding="utf-8") as f:
            f.write(text)

    def pre(self, spec, ports, name, server_dir, install):
        from games import common
        # the game keeps settings in the user's config folder; give each server its own
        return (f'export XDG_CONFIG_HOME="{server_dir}"\n'
                + common.console_pipe_lines(common.console_file(self.log_file(server_dir, install))))

    def stop_lines(self, spec, ports, name, server_dir, install):
        from games import common
        return f'echo "exit" >> "{common.console_file(self.log_file(server_dir, install))}"\n'

    def log_file(self, server_dir, install):
        return os.path.join(server_dir, "server.log")

    def proc_pattern(self, key, ports, server_dir):
        return f"LocalAdmin {ports['game']} --acceptEULA"

    @staticmethod
    def parse_players(text: str) -> list[str] | None:
        """The last answer to the console's `players` command in the log, or None."""
        text = re.sub(r"\x1b\[[0-9;]*m", "", text)
        i = text.rfind("List of players (")
        if i < 0:
            return None
        lines = text[i:].splitlines()
        count = int(re.match(r"List of players \((\d+)\)", lines[0]).group(1))
        names = []
        for line in lines[1:1 + count]:
            m = re.match(r"^(?:\[[^\]]*\]\s*)?-\s*(.+?)\s*$", line)
            if m:
                names.append(m.group(1))
        return names if len(names) == count else [f"Player {n + 1}" for n in range(count)]

    def probe(self, s) -> dict:
        from games import common
        out = {"players": None, "player_names": [], "player_detail": [],
               "max_players": None, "reachable": None}
        try:   # read the answer to the previous poll's question, then ask again
            with open(s.log_path, "rb") as f:
                f.seek(max(0, os.path.getsize(s.log_path) - 16384))
                names = self.parse_players(f.read().decode("utf-8", "replace"))
        except OSError:
            return out
        common.console_send(s, "players")
        if names is not None:
            out.update(reachable=True, players=len(names), player_names=names,
                       player_detail=[{"name": n, "id": ""} for n in names])
        return out

    def broadcast(self, s, message: str) -> str:
        from games import common
        text = re.sub(r"[\r\n<>]", " ", message)[:200]
        if not common.console_send(s, "/bc 10 " + text):
            raise ActionError(f"Message to {s.name} failed — the server's console isn't available.")
        return "sent"
