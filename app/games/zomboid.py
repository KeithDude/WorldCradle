"""Project Zomboid game type (native Linux dedicated server).

Each server keeps everything (settings, world, players) in its own folder,
selected with the launcher's -cachedir option. Setting names are keys of the
server's <name>.ini; the game fills in every key we don't write with its own
default. Players and controls go through the game's RCON console.
"""
from __future__ import annotations

import os
import re
import time

import monitor
from games import common
from games.base import empty_probe, opt_bool, safe_name
from games.simple import RCON_PORT_HELP, SimpleGame

LAUNCHER = "start-server.sh"
SERVERNAME = "worldcradle"   # names the settings/world files inside the server's own folder
_NAME_RE = re.compile(r'^[^\r\n"\x00-\x1f]{1,64}$')

class ZomboidGame(SimpleGame):
    kind = "zomboid"
    label = "Project Zomboid"
    steam_app = 380870
    exe = LAUNCHER
    install_gb = 6
    ram_note = "about 4-8 GB of memory"
    about = "Slow-burn zombie survival in an open world."
    has_query = False
    kill_signal = "SIGTERM"
    stop_seconds = 90
    rcon_commands = {"save": "save", "broadcast": 'servermsg "{message}"', "kick": 'kickuser "{target}"',
                     "ban": 'banuser "{target}"'}
    # Stop = save over the console, then let systemd send the normal stop signal, which the
    # server handles with a clean shutdown (~20 s). Its own console "quit" was far slower in
    # testing (minutes).
    rcon_save_before_stop = "save"

    port_layout = [
        {"name": "game", "klass": "game", "start": 16261, "span": 2, "proto": "UDP", "forward": True,
         "label": "Game port (UDP)", "help": "The game also uses the next port up. Forward both (UDP)."},
        {"name": "rcon", "klass": "rcon", "start": 27060, "proto": "TCP", "label": "Admin console port (TCP)",
         "help": RCON_PORT_HELP},
    ]
    extra_fields = [
        {"name": "maxplayers", "label": "Max players (1-100)", "type": "number", "min": 1, "max": 100,
         "default": 8},
        {"name": "description", "label": "Description shown in the server list — optional", "placeholder": ""},
        {"name": "public", "label": "List in the game's own server browser (Steam's browser always shows it)", "type": "checkbox",
         "default": False},
        {"name": "pvp", "label": "Players can hurt each other (PvP)", "type": "checkbox", "default": False},
        {"name": "pause_empty", "label": "Pause the world when nobody is online", "type": "checkbox",
         "default": True},
        {"name": "open", "label": "Anyone with the password can join (off = only accounts you create)",
         "type": "checkbox", "default": True},
    ]
    provision_hint = ("Project Zomboid — a new world in its own folder. The join password is the shared "
                      "one; the shared admin password is also the password of the in-game “admin” "
                      "account. World and zombie settings (the game's “sandbox” options) start at the "
                      "defaults. The first start takes a few minutes.")

    def command(self, spec, ports, name, server_dir, install):
        self.option(spec, "maxplayers")
        return (f'./{LAUNCHER} -cachedir="{server_dir}" -servername {SERVERNAME} '
                f'-adminpassword "$GAME_ADMIN_PASSWORD"')

    def write_files(self, spec, ports, name, server_dir, install):
        b = lambda field, default: str(opt_bool(spec, field, default)).lower()  # noqa: E731
        ini = {
            "DefaultPort": ports["game"], "UDPPort": ports["game"] + 1,
            "MaxPlayers": self.option(spec, "maxplayers"),
            "PublicName": name,
            "PublicDescription": safe_name(spec.get("description") or "", 200),
            "Public": b("public", False), "PVP": b("pvp", False),
            "PauseEmpty": b("pause_empty", True), "Open": b("open", True),
            "Password": "set-at-launch",
            "RCONPort": ports["rcon"], "RCONPassword": "set-at-launch",
            "UPnP": "false",
        }
        os.makedirs(os.path.join(server_dir, "Server"), exist_ok=True)
        common.write_private(self._ini(server_dir), "".join(f"{k}={v}\n" for k, v in ini.items()))   # will hold both passwords

    def pre(self, spec, ports, name, server_dir, install):
        return common.password_sync(self._ini(server_dir), [("Password", "join"), ("RCONPassword", "admin")],
                                    add_missing=True)

    @staticmethod
    def _ini(server_dir):
        return os.path.join(server_dir, "Server", SERVERNAME + ".ini")

    def log_file(self, server_dir, install):
        return os.path.join(server_dir, "server-console.txt")

    def proc_pattern(self, spec, ports, server_dir):
        return f"-cachedir={server_dir}"

    def rcon_send(self, s, cmd: str) -> str | None:
        # The game's console serves one request at a time and can drop one that
        # arrives right behind another (e.g. a button press during a poll), so
        # a missed answer gets a second try.
        for attempt in (1, 2):
            r = monitor.rcon_run(s.rcon_port, s.rcon_password, cmd)
            if r is not None:
                return r
            if attempt == 1:
                time.sleep(1.5)
        return None

    @staticmethod
    def parse_players(text: str) -> list[str] | None:
        # "Players connected (2): \n-alice\n-bob\n"
        m = re.search(r"Players connected \((\d+)\)", text or "")
        if not m:
            return None
        return [ln[1:].strip() for ln in text.splitlines() if ln.startswith("-") and ln[1:].strip()]

    def probe(self, s) -> dict:
        out = empty_probe()
        names = self.parse_players(self.rcon_send(s, "players") or "") if s.rcon_port else None
        if names is not None:
            out.update(reachable=True, players=len(names), player_names=names,
                       player_detail=[{"name": n, "id": n} for n in names])
        try:
            ini = open(os.path.join(s.save_root, "Server", SERVERNAME + ".ini"), encoding="utf-8").read()
            m = re.search(r"(?m)^MaxPlayers=(\d+)", ini)
            out["max_players"] = int(m.group(1)) if m else None
        except OSError:
            pass
        return out

    def valid_target(self, target: str) -> bool:
        return bool(_NAME_RE.match(target))

    def broadcast(self, s, message: str) -> str:
        return super().broadcast(s, message.replace('"', "'"))
