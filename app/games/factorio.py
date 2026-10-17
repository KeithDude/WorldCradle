"""Factorio — the official headless server (native Linux), built on games/simple.py.

Not a Steam download: Wube publishes the headless server as a free archive on
factorio.com. One shared install; each server has its own folder (map, mods,
settings). Setting names are keys of the game's server-settings.json. Players
and controls go through the game's RCON console.
"""
from __future__ import annotations

import io
import json
import os
import re
import tarfile
import urllib.request

from games import common
from games.base import ActionError, empty_probe, safe_name
from games.simple import RCON_PORT_HELP, SimpleGame

DOWNLOAD_URL = "https://factorio.com/get-download/stable/headless/linux64"
RELEASES_URL = "https://factorio.com/api/latest-releases"
EXE = "bin/x64/factorio"
_NAME_RE = re.compile(r"^[A-Za-z0-9_.\-]{1,60}$")   # factorio.com usernames
_UA = {"User-Agent": "Mozilla/5.0 (RealmCradle)"}

class FactorioGame(SimpleGame):
    kind = "factorio"
    label = "Factorio"
    exe = EXE
    install_gb = 0.5
    ram_note = "about 1-4 GB of memory; grows with the size of the factory"
    about = "Factory building and automation. Light on resources."
    has_query = False
    # plain text on its console is said to everyone as the server
    rcon_commands = {"save": "/server-save", "broadcast": "{message}",
                     "kick": "/kick {target}", "ban": "/ban {target}"}

    port_layout = [
        {"name": "game", "klass": "game", "start": 34197, "proto": "UDP", "forward": True,
         "label": "Game port (UDP)", "help": "The port players connect to. Forward it."},
        {"name": "rcon", "klass": "rcon", "start": 27070, "proto": "TCP", "label": "Admin console port (TCP)",
         "help": RCON_PORT_HELP},
    ]
    extra_fields = [
        {"name": "maxplayers", "label": "Max players (0 = no limit)", "type": "number", "min": 0,
         "max": 1000, "default": 0},
        {"name": "description", "label": "Description — optional", "placeholder": ""},
        {"name": "auto_pause", "label": "Pause the factory when nobody is online", "type": "checkbox",
         "default": True},
        {"name": "autosave_interval", "label": "Autosave every … minutes (1-120)", "type": "number",
         "min": 1, "max": 120, "default": 10},
        {"name": "verify_users", "label": "Only let in players signed in to a real factorio.com account",
         "type": "checkbox", "default": True},
        {"name": "admins", "label": "In-game admins — factorio.com usernames, comma-separated; optional",
         "placeholder": "yourname"},
    ]
    provision_hint = ("Factorio — a new map in its own folder, generated the first time the server "
                      "starts. The join password is the shared one. The server isn't listed in the "
                      "public browser (that needs a factorio.com login in its settings file); friends "
                      "use “Connect to address”.")

    def install(self, install_dir: str, on_progress=None) -> tuple[bool, str]:
        try:
            buf = io.BytesIO()
            req = urllib.request.Request(DOWNLOAD_URL, headers=_UA)   # the site refuses Python's default agent
            with urllib.request.urlopen(req, timeout=60) as r:
                total = int(r.headers.get("Content-Length") or 0)
                while True:
                    chunk = r.read(1 << 16)
                    if not chunk:
                        break
                    buf.write(chunk)
                    if on_progress and total:
                        on_progress("downloading", 100.0 * buf.tell() / total)
            buf.seek(0)
            os.makedirs(install_dir, exist_ok=True)
            with tarfile.open(fileobj=buf, mode="r:xz") as tf:   # archive root is "factorio/": strip it
                members = []
                for m in tf.getmembers():
                    parts = m.name.split("/", 1)
                    if len(parts) < 2 or parts[0] != "factorio":
                        continue
                    m.name = parts[1]
                    members.append(m)
                tf.extractall(install_dir, members=members, filter="data")
            try:
                with urllib.request.urlopen(urllib.request.Request(RELEASES_URL, headers=_UA), timeout=15) as r:
                    version = json.load(r)["stable"]["headless"]
            except Exception:
                version = "stable"
            with open(os.path.join(install_dir, "version.txt"), "w", encoding="utf-8") as f:
                f.write(version + "\n")
            return True, f"Factorio {version}"
        except Exception as e:
            return False, f"couldn't download the Factorio server from factorio.com: {e}"

    def command(self, spec, ports, name, server_dir, install):
        bad = [a for a in self._admins(spec) if not _NAME_RE.match(a)]
        if bad:
            raise ActionError(f"Not a valid factorio.com username: {bad[0]}")
        return (f'./{EXE} -c "{server_dir}/config.ini" --start-server "{server_dir}/saves/world.zip" \\\n'
                f'    --server-settings "{server_dir}/server-settings.json" \\\n'
                f'    --server-adminlist "{server_dir}/server-adminlist.json" --port {ports["game"]} \\\n'
                f'    --rcon-bind 127.0.0.1:{ports["rcon"]} --rcon-password "$GAME_ADMIN_PASSWORD" \\\n'
                f'    --console-log "{self.log_file(server_dir, install)}"')

    @staticmethod
    def _admins(spec) -> list[str]:
        return [a.strip() for a in (spec.get("admins") or "").split(",") if a.strip()]

    def write_files(self, spec, ports, name, server_dir, install):
        settings = {
            "name": name,
            "description": safe_name(spec.get("description") or "", 200),
            "tags": [],
            "max_players": self.option(spec, "maxplayers"),
            "visibility": {"public": False, "lan": True},
            "username": "", "password": "", "token": "",
            "game_password": "set-at-launch",
            "require_user_verification": self.option(spec, "verify_users"),
            "auto_pause": self.option(spec, "auto_pause"),
            "autosave_interval": self.option(spec, "autosave_interval"),
            "autosave_slots": 5,
        }
        os.makedirs(os.path.join(server_dir, "saves"), exist_ok=True)
        common.write_private(os.path.join(server_dir, "server-settings.json"),   # will hold the join password
                             json.dumps(settings, indent=2))
        # in-game admins are their own file, not a server-settings.json entry
        with open(os.path.join(server_dir, "server-adminlist.json"), "w", encoding="utf-8") as f:
            json.dump(self._admins(spec), f)
        with open(os.path.join(server_dir, "config.ini"), "w", encoding="utf-8") as f:
            # game files are read from the shared install; everything written stays in this folder
            f.write("[path]\nread-data=__PATH__executable__/../../data\n"
                    f"write-data={server_dir}\n")

    def pre(self, spec, ports, name, server_dir, install):
        world = f"{server_dir}/saves/world.zip"
        return (common.json_password_sync(os.path.join(server_dir, "server-settings.json"),
                                          [(("game_password",), "join")])
                + "# first start: create the map\n"
                f'[ -f "{world}" ] || "{install}/{EXE}" -c "{server_dir}/config.ini" --create "{world}" || exit 1\n')

    def log_file(self, server_dir, install):
        return os.path.join(server_dir, "console.log")

    def proc_pattern(self, spec, ports, server_dir):
        return f"-c {server_dir}/config.ini"

    @staticmethod
    def parse_players(text: str) -> list[str] | None:
        # "Online players (2):\n  alice (online)\n  bob (online)\n"
        if not re.search(r"Online players \(\d+\)", text or ""):
            return None
        return [m.group(1) for m in re.finditer(r"(?m)^\s+(\S+) \(online\)\s*$", text)]

    def probe(self, s) -> dict:
        out = empty_probe()
        names = self.parse_players(self.rcon_send(s, "/players online") or "") if s.rcon_port else None
        if names is not None:
            out.update(reachable=True, players=len(names), player_names=names,
                       player_detail=[{"name": n, "id": n} for n in names])
        try:
            limit = json.load(open(os.path.join(s.save_root, "server-settings.json"),
                                   encoding="utf-8")).get("max_players")
            out["max_players"] = limit or None   # 0 = unlimited
        except (OSError, ValueError):
            pass
        return out

    def valid_target(self, target: str) -> bool:
        return bool(_NAME_RE.match(target))
