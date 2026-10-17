"""Minecraft: Bedrock Edition game type (official dedicated server, native Linux).

For players on phones, tablets, consoles and Windows' Bedrock edition. Not a
Steam download: Mojang publishes the server as a zip. One shared install; each
server has its own folder (settings, allow-list, worlds) that links back to
the shared game files. Setting names are server.properties keys. Admin commands
go to the server's console; who is online is read from its output.
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
from games.base import ActionError, empty_probe, opt_bool
from games.simple import SimpleGame

LINKS_URL = "https://net-secondary.web.minecraft-services.net/api/v1.0/download/links"
EXE = "bedrock_server"
GAMEMODES = [["survival", "Survival"], ["creative", "Creative"], ["adventure", "Adventure"]]
DIFFICULTIES = [["peaceful", "Peaceful (no monsters)"], ["easy", "Easy"], ["normal", "Normal"],
                ["hard", "Hard"]]
# things each server owns; everything else in its folder is a link to the shared install
UDP_SPAN = 10   # UDP ports reserved per server for player connections
_OWN = {"server.properties", "allowlist.json", "permissions.json", "worlds", "valid_known_packs.json"}
_TAG_RE = re.compile(r"^[A-Za-z0-9 _]{1,16}$")   # Xbox gamertags
_EVENTS = re.compile(r"Player connected: (?P<joined>[^,\r\n]+), xuid|Player disconnected: (?P<left>[^,\r\n]+), xuid")
_UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) GameDash", "Accept-Language": "en-US,en;q=0.8"}

def _tags(spec: dict) -> list[str]:
    return [n.strip() for n in (spec.get("allowlist_names") or "").split(",") if n.strip()]


class BedrockGame(SimpleGame):
    kind = "bedrock"
    label = "Minecraft Bedrock"
    title = "Minecraft: Bedrock Edition"
    exe = EXE
    has_query = False
    pre_lines = "export LD_LIBRARY_PATH=.\n"   # its libraries sit next to it
    console_commands = {"broadcast": "say {message}", "kick": 'kick "{target}"'}
    quit_command = "stop"          # saves the world, then quits
    stopped_line = "Quit correctly"
    install_gb = 0.6
    ram_note = "about 1-2 GB of memory"
    about = "Minecraft for consoles, phones, tablets and Windows (Bedrock). Not compatible with Java Edition."
    port_layout = [
        {"name": "game", "klass": "game", "start": 19132, "proto": "UDP and TCP", "forward": True,
         "label": "Game port (UDP and TCP)",
         "help": "The address players type in. Forward it for both UDP and TCP, as Microsoft's guide does."},
        {"name": "udp", "klass": "game", "start": 19140, "span": UDP_SPAN, "proto": "UDP", "forward": True,
         "label": f"Player data ports (UDP, {UDP_SPAN} in a row)",
         "help": "Game data flows over these once a player has connected. Forward the whole range (UDP)."},
        {"name": "game6", "klass": "game", "start": 19133, "proto": "UDP", "label": "Unused legacy port",
         "form": False},
    ]
    extra_fields = [
        {"name": "maxplayers", "label": "Max players (1-100)", "type": "number", "min": 1, "max": 100,
         "default": 10},
        {"name": "gamemode", "label": "Game mode", "type": "select", "options": GAMEMODES,
         "default": "survival"},
        {"name": "difficulty", "label": "Difficulty", "type": "select", "options": DIFFICULTIES,
         "default": "easy"},
        {"name": "allowlist", "label": "Only let in players I've added to the allow-list",
         "type": "checkbox", "default": True,
         "help": "Minecraft has no join password — the allow-list is how you keep strangers out."},
        {"name": "allowlist_names", "label": "Players to allow — Xbox gamertags, comma-separated",
         "placeholder": "Alex, Steve"},
        {"name": "cheats", "label": "Allow cheats (commands)", "type": "checkbox", "default": False},
        {"name": "seed", "label": "World seed — optional", "placeholder": "leave blank for a random world"},
    ]
    provision_hint = ("Minecraft Bedrock — a new world in its own folder. There is no join password: "
                      "use the allow-list to control who can join. Console players add the server by "
                      "address; some consoles need a workaround to join servers that aren't on the "
                      "featured list.")

    def install(self, install_dir: str, on_progress=None) -> tuple[bool, str]:
        try:
            with urllib.request.urlopen(urllib.request.Request(LINKS_URL, headers=_UA), timeout=30) as r:
                links = json.load(r)["result"]["links"]
            url = next(x["downloadUrl"] for x in links if x["downloadType"] == "serverBedrockLinux")
            if not re.match(r"^https://www\.minecraft\.net/bedrockdedicatedserver/bin-linux/bedrock-server-[\d.]+\.zip$", url):
                return False, "Mojang returned an unexpected download address"
            buf = io.BytesIO()
            with urllib.request.urlopen(urllib.request.Request(url, headers=_UA), timeout=120) as r:
                total = int(r.headers.get("Content-Length") or 0)
                while True:
                    chunk = r.read(1 << 16)
                    if not chunk:
                        break
                    buf.write(chunk)
                    if on_progress and total:
                        on_progress("downloading", 100.0 * buf.tell() / total)
            os.makedirs(install_dir, exist_ok=True)
            real = os.path.realpath(install_dir)
            with zipfile.ZipFile(buf) as z:
                for info in z.infolist():
                    dst = os.path.realpath(os.path.join(real, info.filename))
                    if not dst.startswith(real + os.sep):
                        continue   # never write outside the install folder
                    if info.is_dir():
                        os.makedirs(dst, exist_ok=True)
                        continue
                    os.makedirs(os.path.dirname(dst), exist_ok=True)
                    with z.open(info) as src, open(dst, "wb") as out:
                        shutil.copyfileobj(src, out)
            os.chmod(os.path.join(install_dir, EXE), 0o755)
            version = url.rsplit("bedrock-server-", 1)[1][:-4]
            with open(os.path.join(install_dir, "version.txt"), "w", encoding="utf-8") as f:
                f.write(version + "\n")
            return True, f"Minecraft Bedrock {version}"
        except Exception as e:
            return False, f"couldn't download the Bedrock server from Mojang: {e}"

    def command(self, spec: dict, ports: dict, name: str, server_dir: str, install: str) -> str:
        bad = [n for n in _tags(spec) if not _TAG_RE.match(n)]
        if bad:
            raise ActionError(f"Not a valid Xbox gamertag: {bad[0]}")
        if not re.match(r"^[\w \-]{0,64}$", (spec.get("seed") or "").strip()):
            raise ActionError("World seed: letters, digits, spaces, - and _ only (up to 64).")
        return f"./{EXE}"

    def write_files(self, spec: dict, ports: dict, name: str, server_dir: str, install: str) -> None:
        b = lambda field, default: str(opt_bool(spec, field, default)).lower()  # noqa: E731
        values = {
            "server-name": name.replace(";", " "), "level-name": "world",
            "gamemode": self.option(spec, "gamemode"),
            "difficulty": self.option(spec, "difficulty"),
            "allow-cheats": b("cheats", False),
            "max-players": self.option(spec, "maxplayers"),
            "online-mode": "true",            # verify players with Xbox Live (blocks impersonation)
            "allow-list": b("allowlist", True),
            "server-port": ports["game"], "server-portv6": ports["game6"],
            # "nethernet" is the only mode current game clients can join. Players
            # first reach server-port (TCP), then exchange game data over the UDP
            # range below — the router must forward both. LAN broadcast is off: it
            # uses one fixed port, which clashes when two servers run here.
            "transport": "nethernet", "enable-lan-visibility": "false",
            "server-udp-ports": f"{ports['udp']}-{ports['udp'] + UDP_SPAN - 1}",
            "level-seed": (spec.get("seed") or "").strip(),
        }
        # start from the settings file shipped with this version, so every other default is right
        props = open(os.path.join(install, "server.properties"), encoding="utf-8").read()
        for k, v in values.items():
            pat = re.compile(r"(?m)^%s=.*$" % re.escape(k))
            line = f"{k}={v}"
            props = pat.sub(lambda m: line, props) if pat.search(props) else props + line + "\n"
        os.makedirs(os.path.join(server_dir, "worlds"), exist_ok=True)
        for entry in os.listdir(install):   # link the shared game files into the server's folder
            if entry in _OWN or entry.startswith("gamedash-") or entry in ("version.txt",):
                continue
            link = os.path.join(server_dir, entry)
            if not os.path.lexists(link):
                os.symlink(os.path.join(install, entry), link)
        with open(os.path.join(server_dir, "server.properties"), "w", encoding="utf-8") as f:
            f.write(props)
        with open(os.path.join(server_dir, "allowlist.json"), "w", encoding="utf-8") as f:
            json.dump([{"ignoresPlayerLimit": False, "name": t} for t in _tags(spec)], f, indent=2)
        with open(os.path.join(server_dir, "permissions.json"), "w", encoding="utf-8") as f:
            f.write("[]\n")

    def work_dir(self, server_dir: str, install: str) -> str:
        return server_dir      # it reads its settings and worlds from the folder it runs in

    def save_dir(self, server_dir: str, install: str) -> str:
        return os.path.join(server_dir, "worlds")

    def log_file(self, server_dir: str, install: str) -> str:
        return os.path.join(server_dir, "server.log")

    def proc_pattern(self, spec: dict, ports: dict, server_dir: str) -> str:
        return f"{server_dir}/server.log.console"   # the console feeder identifies this server

    def save_paths(self, s) -> list[dict]:
        if not s.save_root:
            return []
        d = os.path.dirname(s.save_root)
        return [{"path": s.save_root, "role": "save"}] + [
            {"path": os.path.join(d, f), "role": "save"} for f in ("server.properties", "allowlist.json", "permissions.json")]

    def probe(self, s) -> dict:
        out = empty_probe(reachable=monitor.port_listening(s.game_port))
        names = monitor.roster_from_log(s.log_path, _EVENTS) if s.log_path else None
        if names is not None:
            out.update(players=len(names), player_names=names,
                       player_detail=[{"name": n, "id": n} for n in names])
        try:
            props = open(os.path.join(os.path.dirname(s.save_root), "server.properties"), encoding="utf-8").read()
            m = re.search(r"(?m)^max-players=(\d+)", props)
            out["max_players"] = int(m.group(1)) if m else None
        except OSError:
            pass
        return out

    def valid_target(self, target: str) -> bool:
        return bool(_TAG_RE.match(target))
