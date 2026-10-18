"""Minecraft: Java Edition game type.

Not a Steam game: the official server is one .jar downloaded from Mojang, run
with Java. One shared jar serves every server; each server has its own folder
(world, server.properties, whitelist). Settings names are server.properties
keys. Players, save, broadcast, kick and ban go through the server's RCON.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import urllib.request

import monitor
from games import common
from games.base import ActionError, empty_probe, opt_bool, opt_int
from games.simple import RCON_PORT_HELP, SimpleGame

MANIFEST_URL = "https://piston-meta.mojang.com/mc/game/version_manifest_v2.json"
EULA_URL = "https://aka.ms/MinecraftEULA"
GAMEMODES = [["survival", "Survival"], ["creative", "Creative"], ["adventure", "Adventure"]]
DIFFICULTIES = [["peaceful", "Peaceful (no monsters)"], ["easy", "Easy"], ["normal", "Normal"],
                ["hard", "Hard"]]
WORLD_TYPES = [["minecraft:normal", "Normal"], ["minecraft:flat", "Flat"],
               ["minecraft:large_biomes", "Large biomes"], ["minecraft:amplified", "Amplified"]]
_NAME_RE = re.compile(r"^[A-Za-z0-9_]{1,16}$")
# "There are 2 of a max of 20 players online: Alex, Steve"
_LIST_RE = re.compile(r"There are (\d+) of a max of (\d+) players online:?\s*(.*)", re.S)

def _whitelist_names(spec: dict) -> list[str]:
    return [n.strip() for n in (spec.get("whitelist_names") or "").split(",") if n.strip()]


def _java_major() -> int | None:
    try:
        out = subprocess.run(["java", "-version"], capture_output=True, text=True, timeout=15)
        m = re.search(r'version "(\d+)(?:\.(\d+))?', out.stderr + out.stdout)
        if not m:
            return None
        major = int(m.group(1))
        return int(m.group(2)) if major == 1 and m.group(2) else major   # "1.8" → 8
    except Exception:
        return None


class MinecraftGame(SimpleGame):
    join_steps = [
        "In Minecraft: Java Edition: <b>Multiplayer → Add Server</b>.",
        "Server Address: <code>{address}</code>",
        "There is no password — the server owner has to add your Minecraft username to its whitelist first.",
    ]
    kind = "minecraft"
    label = "Minecraft"
    title = "Minecraft: Java Edition"
    exe = "server.jar"
    servers_folder = "servers"
    has_query = False
    rcon_commands = {"save": "save-all", "broadcast": "say {message}", "kick": "kick {target}",
                     "ban": "ban {target}"}
    rcon_quit_command = "stop"   # saves the world, then exits
    install_gb = 0.1
    requires = ["java"]
    ram_note = "about 2-4 GB of memory for a few players"
    about = "The original block-building game (Java Edition). Players need the Java Edition of Minecraft."
    port_layout = [
        {"name": "game", "klass": "game", "start": 25565, "proto": "TCP", "forward": True, "label": "Game port (TCP)",
         "help": "The port players connect to. Forward it (TCP)."},
        {"name": "rcon", "klass": "rcon", "start": 25585, "label": "Admin console port (TCP)",
         "help": RCON_PORT_HELP},
    ]
    extra_fields = [
        {"name": "memory", "label": "Memory for this server, in GB (1-32)", "type": "number",
         "min": 1, "max": 32, "default": 2,
         "help": "2 GB suits a handful of players; add more for many players or big builds."},
        {"name": "maxplayers", "label": "Max players (1-200)", "type": "number", "min": 1, "max": 200,
         "default": 10},
        {"name": "gamemode", "label": "Game mode", "type": "select", "options": GAMEMODES,
         "default": "survival"},
        {"name": "difficulty", "label": "Difficulty", "type": "select", "options": DIFFICULTIES,
         "default": "easy"},
        {"name": "hardcore", "label": "Hardcore (one life)", "type": "checkbox", "default": False},
        {"name": "pvp", "label": "Players can hurt each other (PvP)", "type": "checkbox", "default": True},
        {"name": "whitelist", "label": "Only let in players I've added to the whitelist",
         "type": "checkbox", "default": True,
         "help": "Minecraft has no join password — the whitelist is how you keep strangers out. "
                 "Add players below, or later from the server's own console."},
        {"name": "whitelist_names", "label": "Players to allow — Minecraft usernames, comma-separated",
         "placeholder": "Alex, Steve"},
        {"name": "world_type", "label": "World type", "type": "select", "options": WORLD_TYPES,
         "default": "minecraft:normal"},
        {"name": "seed", "label": "World seed — optional", "placeholder": "leave blank for a random world"},
        {"name": "command_blocks", "label": "Allow command blocks", "type": "checkbox", "default": False},
        {"name": "view_distance", "label": "View distance in chunks (3-32, blank = 10)", "type": "number",
         "min": 3, "max": 32, "placeholder": "10",
         "help": "How far players can see. Higher values need noticeably more memory and CPU."},
    ]
    provision_hint = ("Minecraft (Java Edition) — a new world in its own folder. Minecraft has no join "
                      "password, so the shared one doesn't apply here: use the whitelist to control who "
                      "can join. The shared admin password protects the admin console the dashboard uses.")

    # ---- install (not Steam: fetch the official jar from Mojang) -----------
    def install(self, install_dir: str, on_progress=None) -> tuple[bool, str]:
        try:
            with urllib.request.urlopen(MANIFEST_URL, timeout=30) as r:
                manifest = json.load(r)
            version = manifest["latest"]["release"]
            meta_url = next(v["url"] for v in manifest["versions"] if v["id"] == version)
            with urllib.request.urlopen(meta_url, timeout=30) as r:
                meta = json.load(r)
            need = (meta.get("javaVersion") or {}).get("majorVersion")
            have = _java_major()
            if need and have and have < need:
                return False, (f"Minecraft {version} needs Java {need} or newer, and this computer "
                               f"has Java {have}. Update Java, then try again.")
            dl = meta["downloads"]["server"]
            os.makedirs(install_dir, exist_ok=True)
            tmp = os.path.join(install_dir, "server.jar.part")
            sha, got = hashlib.sha1(), 0
            with urllib.request.urlopen(dl["url"], timeout=60) as r, open(tmp, "wb") as f:
                while True:
                    chunk = r.read(1 << 16)
                    if not chunk:
                        break
                    f.write(chunk)
                    sha.update(chunk)
                    got += len(chunk)
                    if on_progress:
                        on_progress("downloading", 100.0 * got / max(1, dl["size"]))
            if sha.hexdigest() != dl["sha1"]:   # never run a jar that isn't the one Mojang published
                os.unlink(tmp)
                return False, "the download was damaged (checksum mismatch) — please try again"
            os.replace(tmp, os.path.join(install_dir, "server.jar"))
            with open(os.path.join(install_dir, "version.txt"), "w", encoding="utf-8") as f:
                f.write(version + "\n")
            return True, f"Minecraft {version}"
        except Exception as e:
            return False, f"couldn't download the Minecraft server from Mojang: {e}"

    # ---- provisioning ------------------------------------------------------
    def command(self, spec: dict, ports: dict, name: str, server_dir: str, install: str) -> str:
        if not shutil.which("java"):
            raise ActionError("Java isn't installed on this computer — Minecraft needs it.")
        bad = [n for n in _whitelist_names(spec) if not _NAME_RE.match(n)]
        if bad:
            raise ActionError(f"Not a valid Minecraft username: {bad[0]} (letters, digits and _ only, "
                              f"up to 16 characters).")
        if not re.match(r"^[\w \-]{0,64}$", (spec.get("seed") or "").strip()):
            raise ActionError("World seed: letters, digits, spaces, - and _ only (up to 64).")
        opt_int(spec, "view_distance", 10, 3, 32, "View distance")
        ram = self.option(spec, "memory")
        # the -D label does nothing in the game; it lets the dashboard tell this server's process apart
        return (f"java -Xms{ram}G -Xmx{ram}G -Dworldcradle.server={self.proc_pattern(spec, ports, server_dir)} "
                f'-jar "{os.path.join(install, self.exe)}" nogui')

    def write_files(self, spec: dict, ports: dict, name: str, server_dir: str, install: str) -> None:
        b = lambda field, default: str(opt_bool(spec, field, default)).lower()  # noqa: E731
        whitelist = str(self.option(spec, "whitelist")).lower()
        props = {
            "motd": name,
            "server-port": ports["game"],
            "max-players": self.option(spec, "maxplayers"),
            "gamemode": self.option(spec, "gamemode"),
            "difficulty": self.option(spec, "difficulty"),
            "hardcore": b("hardcore", False),
            "white-list": whitelist, "enforce-whitelist": whitelist,
            "level-type": self.option(spec, "world_type").replace(":", "\\:"),
            "level-seed": (spec.get("seed") or "").strip(),
            "view-distance": opt_int(spec, "view_distance", 10, 3, 32, "View distance"),
            "online-mode": "true",          # verify accounts with Mojang (blocks impersonation)
            "enable-rcon": "true", "rcon.port": ports["rcon"],
            "rcon.password": "set-at-launch",   # the run script fills in the real one
            "enable-query": "false",
        }
        common.write_private(os.path.join(server_dir, "server.properties"),   # will hold the RCON password
                             "".join(f"{k}={v}\n" for k, v in props.items()))
        with open(os.path.join(server_dir, "eula.txt"), "w", encoding="utf-8") as f:
            f.write(f"# Accepted in WorldCradle's Add-a-server form by the operator ({EULA_URL})\neula=true\n")
        # PvP and command blocks stopped being server.properties settings (Minecraft 1.21.9);
        # they are game rules now, set through the admin console once the server is up (see probe).
        with open(os.path.join(server_dir, "worldcradle-gamerules.txt"), "w", encoding="utf-8") as f:
            f.write(f"gamerule pvp {b('pvp', True)}\n"
                    f"gamerule command_blocks_work {b('command_blocks', False)}\n")
        names = _whitelist_names(spec)
        if names:  # added through the admin console once the server is up (see probe)
            with open(os.path.join(server_dir, "worldcradle-whitelist.txt"), "w", encoding="utf-8") as f:
                f.write("\n".join(names) + "\n")

    def pre(self, spec: dict, ports: dict, name: str, server_dir: str, install: str) -> str:
        # the admin-console (RCON) password, from WorldCradle
        return common.password_sync(os.path.join(server_dir, "server.properties"), [("rcon.password", "admin")])

    def work_dir(self, server_dir: str, install: str) -> str:
        return server_dir      # the world, settings and logs live in the server's own folder

    def proc_pattern(self, spec: dict, ports: dict, server_dir: str) -> str:
        return f"servers/{spec['key']}"

    def log_file(self, server_dir: str, install: str) -> str:
        return os.path.join(server_dir, "logs", "latest.log")

    # ---- monitoring + controls (RCON) --------------------------------------
    def _apply_pending_whitelist(self, s) -> None:
        """First boot: add the names typed on the Add form, then forget the list."""
        path = os.path.join(s.save_root or "", "worldcradle-whitelist.txt")
        if not s.save_root or not os.path.isfile(path):
            return
        names = [n.strip() for n in open(path, encoding="utf-8") if _NAME_RE.match(n.strip())]
        if all(self.rcon_send(s, f"whitelist add {n}") is not None for n in names):
            os.unlink(path)

    def _apply_pending_gamerules(self, s) -> None:
        """First boot: set the game rules chosen on the Add form, then forget the list."""
        path = os.path.join(s.save_root or "", "worldcradle-gamerules.txt")
        if not s.save_root or not os.path.isfile(path):
            return
        lines = [l.strip() for l in open(path, encoding="utf-8")
                 if re.match(r"^gamerule [a-z_]+ (true|false)$", l.strip())]
        if all("is now set to" in (self.rcon_send(s, l) or "") for l in lines):
            os.unlink(path)

    @staticmethod
    def parse_list(text: str) -> tuple[int, int, list[str]] | None:
        m = _LIST_RE.search(re.sub(r"§.", "", text or ""))
        if not m:
            return None
        names = [n.strip() for n in m.group(3).split(",") if n.strip()]
        return int(m.group(1)), int(m.group(2)), names

    def probe(self, s) -> dict:
        out = empty_probe(reachable=monitor.port_listening(s.game_port))
        parsed = self.parse_list(self.rcon_send(s, "list") or "")
        if parsed:
            count, limit, names = parsed
            out.update(players=count, max_players=limit, player_names=names,
                       # Minecraft kicks/bans by name, so the name doubles as the id
                       player_detail=[{"name": n, "id": n} for n in names])
            self._apply_pending_whitelist(s)
            self._apply_pending_gamerules(s)
        return out

    def valid_target(self, target: str) -> bool:
        return bool(_NAME_RE.match(target))
