"""Terraria — the official dedicated server (native Linux), built on games/simple.py.

Not a Steam download: Re-Logic publishes the server as a zip on terraria.org.
One shared install; each server has its own folder (settings file + worlds).
Setting names are serverconfig.txt keys. Admin commands go to the server's
console; who is online is read from its output.
"""
from __future__ import annotations

import io
import json
import os
import re
import shutil
import urllib.request
import zipfile

import monitor
from games import common
from games.base import ActionError, empty_probe, safe_name
from games.simple import SimpleGame, port

NAMES_URL = "https://terraria.org/api/get/dedicated-servers-names"
ZIP_URL = "https://terraria.org/api/download/pc-dedicated-server/"
EXE = "TerrariaServer.bin.x86_64"
SIZES = [["1", "Small"], ["2", "Medium"], ["3", "Large"]]
DIFFICULTIES = [["0", "Classic"], ["1", "Expert"], ["2", "Master"], ["3", "Journey"]]
_EVENTS = re.compile(r"^(?P<joined>[^\r\n]{1,40}?) has joined\.\s*$|^(?P<left>[^\r\n]{1,40}?) has left\.\s*$", re.M)
_UA = {"User-Agent": "Mozilla/5.0 (RealmCradle)"}   # terraria.org refuses the default Python agent

class TerrariaGame(SimpleGame):
    kind = "terraria"
    label = "Terraria"
    exe = EXE
    install_gb = 0.2
    ram_note = "about 1-2 GB of memory"
    about = "2D adventure and building. Very light on resources."
    has_query = False
    survives_connect_test = False   # connecting and hanging up crashes its server
    kill_signal = "SIGTERM"
    servers_folder = "servers"
    console_commands = {"save": "save", "broadcast": "say {message}",
                        "kick": "kick {target}", "ban": "ban {target}"}
    quit_command = "exit"           # saves the world, then quits

    port_layout = [port("game", 7790, "Game port (TCP)", proto="TCP",
                        help="The port players connect to. Forward it (TCP).")]
    extra_fields = [
        {"name": "size", "label": "World size", "type": "select", "options": SIZES, "default": "2"},
        {"name": "difficulty", "label": "Difficulty", "type": "select", "options": DIFFICULTIES,
         "default": "0"},
        {"name": "maxplayers", "label": "Max players (1-255)", "type": "number", "min": 1, "max": 255,
         "default": 8},
        {"name": "seed", "label": "World seed — optional", "placeholder": "leave blank for a random world"},
        {"name": "motd", "label": "Welcome message — optional", "placeholder": ""},
        {"name": "secure", "label": "Extra cheat protection", "type": "checkbox", "default": True},
    ]
    provision_hint = ("Terraria — a new world in its own folder, created the first time the server "
                      "starts (a large world takes a minute or two). The join password is the shared one.")

    def install(self, install_dir: str, on_progress=None) -> tuple[bool, str]:
        try:
            req = urllib.request.Request(NAMES_URL, headers=_UA)
            with urllib.request.urlopen(req, timeout=30) as r:
                name = json.load(r)[0]
            if not re.match(r"^terraria-server-\d+\.zip$", name):
                return False, "terraria.org returned an unexpected file name"
            buf = io.BytesIO()
            with urllib.request.urlopen(urllib.request.Request(ZIP_URL + name, headers=_UA), timeout=60) as r:
                total = int(r.headers.get("Content-Length") or 0)
                while True:
                    chunk = r.read(1 << 16)
                    if not chunk:
                        break
                    buf.write(chunk)
                    if on_progress and total:
                        on_progress("downloading", 100.0 * buf.tell() / total)
            os.makedirs(install_dir, exist_ok=True)
            with zipfile.ZipFile(buf) as z:   # keep only the Linux build, flattened into install_dir
                for info in z.infolist():
                    parts = info.filename.split("/")
                    if len(parts) < 3 or parts[1] != "Linux" or info.is_dir():
                        continue
                    rel = os.path.normpath("/".join(parts[2:]))
                    if rel.startswith("..") or os.path.isabs(rel):
                        continue
                    dst = os.path.join(install_dir, rel)
                    os.makedirs(os.path.dirname(dst), exist_ok=True)
                    with z.open(info) as src, open(dst, "wb") as out:
                        shutil.copyfileobj(src, out)
            os.chmod(os.path.join(install_dir, EXE), 0o755)
            with open(os.path.join(install_dir, "version.txt"), "w", encoding="utf-8") as f:
                f.write(name + "\n")
            return True, name
        except Exception as e:
            return False, f"couldn't download the Terraria server from terraria.org: {e}"

    def command(self, spec, ports, name, server_dir, install):
        if not re.match(r"^[\w \-.]{0,40}$", (spec.get("seed") or "").strip()):
            raise ActionError("World seed: letters, digits, spaces, . - and _ only (up to 40).")
        return f'./{EXE} -config "{server_dir}/serverconfig.txt"'

    def write_files(self, spec, ports, name, server_dir, install):
        world = re.sub(r"[^A-Za-z0-9_]", "_", name)[:40] or "world"
        os.makedirs(os.path.join(server_dir, "worlds"), exist_ok=True)
        cfg = {
            "world": os.path.join(server_dir, "worlds", world + ".wld"),
            "worldpath": os.path.join(server_dir, "worlds"),
            "autocreate": self.option(spec, "size"),
            "worldname": world,
            "difficulty": self.option(spec, "difficulty"),
            "maxplayers": self.option(spec, "maxplayers"),
            "port": ports["game"],
            "password": "set-at-launch",
            "motd": safe_name(spec.get("motd") or "", 120),
            "secure": "1" if self.option(spec, "secure") else "0",
            "upnp": "0",
            # each server keeps its own ban list (the default is one file shared by every server)
            "banlist": os.path.join(server_dir, "banlist.txt"),
        }
        seed = (spec.get("seed") or "").strip()
        if seed:
            cfg["seed"] = seed
        common.write_private(os.path.join(server_dir, "serverconfig.txt"),   # will hold the join password
                             "".join(f"{k}={v}\n" for k, v in cfg.items()))

    def pre(self, spec, ports, name, server_dir, install):
        return common.password_sync(os.path.join(server_dir, "serverconfig.txt"), [("password", "join")])

    def log_file(self, server_dir, install):
        return os.path.join(server_dir, "server.log")

    def proc_pattern(self, spec, ports, server_dir):
        return f"-config {server_dir}/serverconfig.txt"

    def probe(self, s) -> dict:
        out = empty_probe(reachable=monitor.port_listening(s.game_port))
        names = monitor.roster_from_log(s.log_path, _EVENTS) if s.log_path else None
        if names is not None:
            out.update(players=len(names), player_names=names,
                       player_detail=[{"name": n, "id": n} for n in names])   # kicked/banned by name
        try:
            m = re.search(r"(?m)^maxplayers=(\d+)", open(os.path.join(s.save_root, "serverconfig.txt"),
                                                         encoding="utf-8").read())
            out["max_players"] = int(m.group(1)) if m else None
        except OSError:
            pass
        return out

    def valid_target(self, target: str) -> bool:
        return bool(re.match(r"^[^\r\n\x00-\x1f]{1,20}$", target))
