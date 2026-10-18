"""ARK: Survival Evolved game type."""
from __future__ import annotations

import os
import re

import config
import monitor
from games.base import ActionError, empty_probe
from games.simple import RCON_PORT_HELP, SimpleGame

ARK_EXEC = "./ShooterGame/Binaries/Linux/ShooterGameServer"
# Official maps: (map code for the launch line, display name, folder under
# ShooterGame/Content that exists when the map is installed).
ARK_MAPS = [
    ("TheIsland", "The Island", "Maps/TheIslandSubMaps"),
    ("TheCenter", "The Center", "Mods/TheCenter"),
    ("ScorchedEarth_P", "Scorched Earth", "Maps/ScorchedEarth"),
    ("Ragnarok", "Ragnarok", "Mods/Ragnarok"),
    ("Aberration_P", "Aberration", "Maps/Aberration"),
    ("Extinction", "Extinction", "Maps/Extinction"),
    ("Valguero_P", "Valguero", "Mods/Valguero"),
    ("Genesis", "Genesis: Part 1", "Maps/Genesis"),
    ("CrystalIsles", "Crystal Isles", "Mods/CrystalIsles"),
    ("Gen2", "Genesis: Part 2", "Maps/Genesis2"),
    ("LostIsland", "Lost Island", "Mods/LostIsland"),
    ("Fjordur", "Fjordur", "Mods/FjordurOfficial"),
]
WORLDCRADLE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class ArkGame(SimpleGame):
    join_steps = [
        "In Steam: <b>View → Game Servers → “Favorites” tab → “Add a Server”</b>.",
        "Enter this address and add it: <code>{address}</code>",
        "Launch ARK and choose <b>“Join ARK”</b>.",
        "Switch the session filter to <b>“Favorites”</b> — your added server shows up there.",
        "Select <b>{server}</b> and join. {password}",
    ]
    kind = "ark"
    label = "ARK"
    title = "ARK: Survival Evolved"
    exe = "ShooterGame/Binaries/Linux/ShooterGameServer"
    # its maps save by name (AltSaveDirectoryName) in the shared install; the cluster folder holds
    # what travels between maps
    own_folder = False
    stop_seconds = 130           # it saves on exit
    install_gb = 26
    ram_note = "about 6-8 GB of memory per running map"
    about = "Survival with dinosaurs. Each map is its own server; maps in a cluster share characters."
    steam_app = 376030
    update_script = "UpdateArkServer.sh"
    rcon_commands = {"save": "SaveWorld", "broadcast": "ServerChat {message}", "kick": "KickPlayer {target}",
                     "ban": "BanPlayer {target}"}
    rcon_quit_command = ("SaveWorld", "DoExit")
    actions = {"save", "broadcast", "kick", "ban", "chat"}   # chat: its in-game chat, read over RCON
    provision_hint = ("ARK — adds a new map to your cluster (characters & dinos transfer between "
                      "maps in the same cluster). Ports, save folder and the cluster launch are "
                      "generated for you; the join/admin passwords are the shared ones. Rates, decay "
                      "and other gameplay settings come from the cluster's shared Game.ini / "
                      "GameUserSettings.ini. First boot takes ~5 minutes.")

    @staticmethod
    def installed_maps() -> list[list[str]]:
        content = os.path.join(config.install_dir("ark"), "ShooterGame", "Content")
        maps = [[code, label] for code, label, sub in ARK_MAPS
                if os.path.isdir(os.path.join(content, sub))]
        return maps or [[code, label] for code, label, _ in ARK_MAPS]

    @property
    def extra_fields(self) -> list[dict]:
        return [
            {"name": "map", "label": "Map", "type": "select", "options": self.installed_maps(),
             "default": self.installed_maps()[0][0], "help": "Official maps found in this install."},
            {"name": "map_custom", "label": "Custom map code — mod maps only (overrides Map)",
             "placeholder": "", "help": "The map's code as used on the launch line; needs its mod ID below."},
            {"name": "maxplayers", "label": "Max players (1-127)", "type": "number",
             "min": 1, "max": 127, "default": 10},
            {"name": "mode", "label": "Game mode", "type": "select",
             "options": [["pve", "PvE"], ["pvp", "PvP"]], "default": "pve",
             "help": "Pinned on the launch line as ServerPVE."},
            {"name": "difficulty", "label": "Difficulty override (blank = cluster setting)",
             "type": "number", "min": 0.5, "max": 20, "step": 0.5, "placeholder": "5.0",
             "help": "OverrideOfficialDifficulty — 5.0 gives max wild dino level 150."},
            {"name": "mods", "label": "Mod IDs — optional, comma-separated Workshop IDs",
             "placeholder": "731604991,1404697612",
             "help": "Sets GameModIds and -automanagedmods so the server downloads them."},
            {"name": "battleye", "label": "BattlEye anti-cheat", "type": "checkbox", "default": True,
             "help": "Unticked launches with -NoBattlEye."},
            {"name": "crossplay", "label": "Allow Epic Games players (crossplay)",
             "type": "checkbox", "default": False},
            {"name": "cluster_id", "label": "Cluster ID (blank = the configured default)",
             "placeholder": "worldcradle",
             "help": "Maps with the same cluster ID can transfer characters and dinos."},
            {"name": "savedir", "label": "Save folder name (blank = wc_<key>)", "placeholder": "wc_<key>"},
        ]

    port_layout = [
        # leaves the conventional 7777-7783 range for existing maps
        {"name": "game", "klass": "game", "start": 7790, "span": 2,
         "proto": "UDP", "forward": True, "label": "Game port (UDP)", "help": "ARK also uses the next port up (raw socket). Forward both."},
        {"name": "query", "klass": "query", "start": 27030, "proto": "UDP", "forward": True, "label": "Steam query port (UDP)",
         "help": "The port players add in Steam's server browser. Forward it."},
        {"name": "rcon", "klass": "rcon", "start": 27040, "proto": "TCP", "label": "RCON port (TCP)",
         "help": RCON_PORT_HELP},
    ]

    # ---- the launch ------------------------------------------------------------------------
    @staticmethod
    def _cluster_id(spec) -> str:
        cid = (spec.get("cluster_id") or "").strip() or config.load().get("ark_cluster_id") or "worldcradle"
        if not re.match(r"^[A-Za-z0-9_]{1,40}$", cid):
            raise ActionError("Cluster ID must be letters/digits/underscores.")
        return cid

    @staticmethod
    def _save(spec) -> str:
        """Its save folder's name (AltSaveDirectoryName)."""
        save = (spec.get("savedir") or "").strip() or f"wc_{spec['key'].replace('-', '_')}"
        if not re.match(r"^[A-Za-z0-9_]{1,40}$", save):
            raise ActionError("Save folder name must be letters/digits/underscores.")
        return save

    @staticmethod
    def _map(spec) -> str:
        mapcode = ((spec.get("map_custom") or "").strip() or (spec.get("map") or "").strip()
                   or ArkGame.installed_maps()[0][0])          # blank: the first map this install has
        if not re.match(r"^[A-Za-z0-9_]{3,40}$", mapcode):
            raise ActionError("Map code must be 3-40 letters/digits/underscores (e.g. TheCenter).")
        return mapcode

    @staticmethod
    def _mods(spec, pattern=r"^\d{6,12}(,\d{6,12})*$", what="Workshop numbers") -> str:
        mods = "".join((spec.get("mods") or "").split())
        if mods and not re.match(pattern, mods):
            raise ActionError(f"Mod IDs must be {what} separated by commas.")
        return mods

    def session_name(self, spec, name) -> str:
        return config.load().get("server_name_prefix", "") + name   # optional prefix (Settings → General)

    def cluster_dir(self, install) -> str:
        return os.path.join(install, "cluster")

    def command(self, spec, ports, name, server_dir, install):
        mods = self._mods(spec)
        difficulty = self.option(spec, "difficulty")
        opts = (f"{self._map(spec)}?listen?SessionName={self.session_name(spec, name)}?MaxPlayers={self.option(spec, 'maxplayers')}"
                "?ServerPassword=${GAME_SERVER_PASSWORD}?ServerAdminPassword=${GAME_ADMIN_PASSWORD}"
                f"?Port={ports['game']}?QueryPort={ports['query']}?RCONEnabled=True?RCONPort={ports['rcon']}"
                f"?AltSaveDirectoryName={self._save(spec)}"
                f"?ServerPVE={'True' if self.option(spec, 'mode') == 'pve' else 'False'}")
        if difficulty is not None:
            opts += f"?OverrideOfficialDifficulty={difficulty:.1f}"
        if mods:
            opts += f"?GameModIds={mods}"
        flags = (" -automanagedmods" if mods else "") + ("" if self.option(spec, "battleye") else " -NoBattlEye")
        if self.option(spec, "crossplay"):
            # Epic players connect to an address the server must be told: this network's public one
            flags += " -crossplay${EPIC_IP:+ -PublicIPForEpic=$EPIC_IP}"
        return (f'{ARK_EXEC} \\\n  "{opts}" \\\n'
                f'  -server -log -clusterid={self._cluster_id(spec)} '
                f'-ClusterDirOverride="{self.cluster_dir(install)}" -NoTransferFromFiltering{flags}')

    def pre(self, spec, ports, name, server_dir, install):
        epic = ("EPIC_IP=$(python3 -c 'import urllib.request, socket\n"
                "for u in (\"https://api.ipify.org\", \"https://checkip.amazonaws.com\"):\n"
                "    try:\n"
                "        ip = urllib.request.urlopen(u, timeout=6).read(64).decode().strip(); socket.inet_aton(ip); print(ip); break\n"
                "    except Exception:\n"
                "        pass')\n") if self.option(spec, "crossplay") else ""
        return f'mkdir -p "{self.cluster_dir(install)}"\n' + epic

    def proc_pattern(self, spec, ports, server_dir):
        return f"AltSaveDirectoryName={self._save(spec)}?"

    def provision(self, spec: dict, ports: dict) -> dict:
        if not spec.get("name"):
            spec = {**spec, "name": self._map(spec)}    # a map is named after itself by default
        out = super().provision(spec, ports)
        out.update(server_name=self.session_name(spec, out["server_name"]),
                   join_port=ports.get("query", ports["game"]),   # players add it in Steam by its query port
                   save_dir=self._save(spec), cluster_id=self._cluster_id(spec))   # for backups
        return out

    def save_paths(self, s) -> list[dict]:
        install = s.install_dir or config.install_dir(self.kind)   # (ASA reuses this)
        out = []
        if s.save_dir:  # the map's AltSaveDirectoryName under ShooterGame/Saved
            out.append({"path": os.path.join(install, "ShooterGame", "Saved", s.save_dir),
                        "role": "save"})
        if s.cluster_id:  # shared cluster dir (transferred chars/dinos) — shared by ALL maps
            cl = os.path.join(install, "cluster")
            if os.path.isdir(cl):
                out.append({"path": cl, "role": "cluster"})
        return out

    def probe(self, s) -> dict:
        out = empty_probe()
        entries = []
        count = None
        resp = self.rcon_send(s, "ListPlayers")
        if resp is not None:
            out["reachable"] = True        # its admin console answered (ARK Ascended has no Steam query)
            entries = monitor.parse_ark_players(resp)
            count = len(entries)
        info = monitor.a2s_info(s.query_port)
        if info is not None:
            out["reachable"] = True
            out["max_players"] = info["max_players"]
            if count is None:  # no RCON count — fall back to A2S
                count = info["players"]
                if not entries:
                    entries = [{"name": n, "id": ""} for n in monitor.a2s_player_names(s.query_port)]
        out["players"] = count
        out["player_names"] = [e["name"] for e in entries]
        out["player_detail"] = entries
        return out

    def chat(self, s) -> str:
        r = self.rcon_send(s, "GetChat")
        t = (r or "").strip()
        if not t or "server received, but no response" in t.lower():
            t = ""
        return t
