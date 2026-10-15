"""ARK: Survival Evolved game type."""
from __future__ import annotations

import os
import re
import sys

import config
import monitor
from games.base import (ActionError, GameType, opt_bool, opt_choice, opt_float,
                        opt_int, safe_name)

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
GAMEDASH_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class ArkGame(GameType):
    kind = "ark"
    label = "ARK"
    title = "Ark: Survival Evolved"
    install_marker = "ShooterGame/Binaries/Linux/ShooterGameServer"
    install_gb = 26
    ram_note = "about 6-8 GB of memory per running map"
    about = "Survival with dinosaurs. Each map is its own server; maps in a cluster share characters."
    steam_app = 376030
    update_script = "UpdateArkServer.sh"
    actions = {"save", "broadcast", "kick", "ban", "chat"}

    # provisioning: a new cluster map from the shared install (own ports/savedir)
    provisionable = True
    base_port = 7790  # leaves the conventional 7777-7783 range for existing maps
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
             "help": "Official maps found in this install."},
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
             "placeholder": "gamedash",
             "help": "Maps with the same cluster ID can transfer characters and dinos."},
            {"name": "savedir", "label": "Save folder name (blank = gd_<key>)", "placeholder": "gd_<key>"},
        ]

    port_layout = [
        {"name": "game", "klass": "game", "start": base_port, "span": 2,
         "proto": "UDP", "forward": True, "label": "Game port (UDP)", "help": "ARK also uses the next port up (raw socket). Forward both."},
        {"name": "query", "klass": "query", "start": 27030, "proto": "UDP", "forward": True, "label": "Steam query port (UDP)",
         "help": "The port players add in Steam's server browser. Forward it."},
        {"name": "rcon", "klass": "rcon", "start": 27040, "proto": "TCP", "label": "RCON port (TCP)",
         "help": "Lets the dashboard control the server (player list, messages, saving). Keep it closed: never forward it on your router — anyone who could reach it could take over the server."},
    ]

    def provision(self, spec: dict, ports: dict) -> dict:
        ARK_DIR = config.install_dir("ark")
        cfg = config.load()
        CLUSTER_ID = (spec.get("cluster_id") or "").strip() or cfg.get("ark_cluster_id") or "gamedash"
        if not re.match(r"^[A-Za-z0-9_]{1,40}$", CLUSTER_ID):
            raise ActionError("Cluster ID must be letters/digits/underscores.")
        prefix = cfg.get("server_name_prefix", "")  # optional, configurable (was hardcoded)
        CLUSTER_DIR = os.path.join(ARK_DIR, "cluster")
        SECRETS = config.secrets_path()
        if not os.path.isdir(ARK_DIR):
            raise ActionError(f"ARK isn't installed ({ARK_DIR} missing).")
        key = spec["key"]
        mapcode = (spec.get("map_custom") or "").strip() or (spec.get("map") or "").strip()
        if not re.match(r"^[A-Za-z0-9_]{3,40}$", mapcode):
            raise ActionError("Map code must be 3-40 letters/digits/underscores (e.g. TheCenter).")
        friendly = safe_name((spec.get("name") or mapcode).strip()) or mapcode
        maxp = opt_int(spec, "maxplayers", 10, 1, 127, "Max players")
        pve = opt_choice(spec, "mode", ("pve", "pvp"), "pve", "Game mode") == "pve"
        difficulty = opt_float(spec, "difficulty", None, 0.5, 20, "Difficulty override")
        mods = "".join((spec.get("mods") or "").split())
        if mods and not re.match(r"^\d{6,12}(,\d{6,12})*$", mods):
            raise ActionError("Mod IDs must be Workshop numbers separated by commas.")
        battleye = opt_bool(spec, "battleye", True)
        crossplay = opt_bool(spec, "crossplay", False)
        gp, qp, rp = ports["game"], ports["query"], ports["rcon"]
        save = (spec.get("savedir") or "").strip() or f"gd_{key.replace('-', '_')}"  # AltSaveDirectoryName
        if not re.match(r"^[A-Za-z0-9_]{1,40}$", save):
            raise ActionError("Save folder name must be letters/digits/underscores.")
        run = os.path.join(ARK_DIR, f"gamedash-{key}-run.sh")
        opts = (
            f"{mapcode}?listen?SessionName={prefix}{friendly}?MaxPlayers={maxp}"
            "?ServerPassword=${GAME_SERVER_PASSWORD}?ServerAdminPassword=${GAME_ADMIN_PASSWORD}"
            f"?Port={gp}?QueryPort={qp}?RCONEnabled=True?RCONPort={rp}?AltSaveDirectoryName={save}"
            f"?ServerPVE={'True' if pve else 'False'}"
        )
        if difficulty is not None:
            opts += f"?OverrideOfficialDifficulty={difficulty:.1f}"
        if mods:
            opts += f"?GameModIds={mods}"
        flags = ""
        if mods:
            flags += " -automanagedmods"
        if not battleye:
            flags += " -NoBattlEye"
        epic = ""
        if crossplay:
            # Epic players connect to an address the server must be told: this network's public one
            flags += ' -crossplay${EPIC_IP:+ -PublicIPForEpic=$EPIC_IP}'
            epic = ("EPIC_IP=$(python3 -c 'import urllib.request, socket\n"
                    "for u in (\"https://api.ipify.org\", \"https://checkip.amazonaws.com\"):\n"
                    "    try:\n"
                    "        ip = urllib.request.urlopen(u, timeout=6).read(64).decode().strip(); socket.inet_aton(ip); print(ip); break\n"
                    "    except Exception:\n"
                    "        pass')\n")
        script = (
            "#!/bin/sh\n"
            f". {SECRETS}\n"
            f'mkdir -p "{CLUSTER_DIR}"\n'
            + epic +
            f'cd "{ARK_DIR}" || exit 1\n'
            f'exec {ARK_EXEC} \\\n'
            f'  "{opts}" \\\n'
            f'  -server -log -clusterid={CLUSTER_ID} '
            f'-ClusterDirOverride="{CLUSTER_DIR}" -NoTransferFromFiltering{flags}\n'
        )
        with open(run, "w", encoding="utf-8") as f:
            f.write(script)
        os.chmod(run, 0o755)
        # graceful stop: RCON SaveWorld + DoExit via gamedash's own helper. Use the
        # running interpreter (the venv python, which has the rcon module) and the
        # absolute path to arkstop.py — robust to wherever the code/venv live.
        stop = os.path.join(ARK_DIR, f"gamedash-{key}-stop.sh")
        with open(stop, "w", encoding="utf-8") as f:
            f.write(
                "#!/bin/sh\n"
                f". {SECRETS}\n"
                f'"{sys.executable}" "{os.path.join(GAMEDASH_DIR, "arkstop.py")}" {rp} "$GAME_ADMIN_PASSWORD"\n'
            )
        os.chmod(stop, 0o755)
        return {
            "exec_start": run, "working_dir": ARK_DIR,
            "game_port": gp, "query_port": qp, "rcon_port": rp,
            "rcon_password_ref": "GAME_ADMIN_PASSWORD",
            "a2s": True, "proc_match": f"{mapcode}?listen",
            "server_name": f"{prefix}{friendly}", "join_port": qp,
            "install_dir": ARK_DIR, "steam_app": 376030,
            "exec_stop": stop, "timeout_stop": 130,  # ARK saves on DoExit
            "save_dir": save, "cluster_id": CLUSTER_ID,  # for backup save_paths
        }

    def save_paths(self, s) -> list[dict]:
        install = s.install_dir or config.install_dir("ark")
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
        out = {"players": None, "player_names": [], "player_detail": [],
               "max_players": None, "reachable": None}
        entries = []
        count = None
        resp = monitor.rcon_run(s.rcon_port, s.rcon_password, "ListPlayers")
        if resp is not None:
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

    def save(self, s) -> str:
        r = monitor.rcon_run(s.rcon_port, s.rcon_password, "SaveWorld")
        if r is None:
            raise ActionError(f"Save to {s.name} failed (no RCON response).")
        return r.strip() or "World Saved"

    def broadcast(self, s, message: str) -> str:
        r = monitor.rcon_run(s.rcon_port, s.rcon_password, "ServerChat " + message)
        if r is None:
            raise ActionError(f"Broadcast to {s.name} failed (no RCON response).")
        return "sent"

    def kick(self, s, target: str) -> str:
        r = monitor.rcon_run(s.rcon_port, s.rcon_password, "KickPlayer " + target)
        if r is None:
            raise ActionError(f"Kick on {s.name} failed (no RCON response).")
        return r.strip() or "ok"

    def ban(self, s, target: str) -> str:
        r = monitor.rcon_run(s.rcon_port, s.rcon_password, "BanPlayer " + target)
        if r is None:
            raise ActionError(f"Ban on {s.name} failed (no RCON response).")
        return r.strip() or "ok"

    def chat(self, s) -> str:
        r = monitor.rcon_run(s.rcon_port, s.rcon_password, "GetChat")
        t = (r or "").strip()
        if not t or "server received, but no response" in t.lower():
            t = ""
        return t
