"""Core Keeper game type (native Linux dedicated server).

Everything is a launch argument (see the server's ARGUMENTS.txt). The server
needs a display to start, so it runs inside a throwaway virtual one (xvfb-run).

Two ways for players to connect:
  * "Game ID" (default): the server registers with Steam's relay and prints a
    Game ID; friends type that ID in the game. No router setup at all.
  * "Direct": the server listens on a port that must be forwarded.
"""
from __future__ import annotations

import os
import re

import monitor
from games.base import ActionError, empty_probe
from games.simple import SimpleGame

EXE = "CoreKeeperServer"
MODES = [["Normal", "Normal"], ["Hard", "Hard"], ["Casual", "Casual (gentler monsters)"],
         ["Creative", "Creative"]]
CONNECT = [["relay", "Game ID — friends type a code; no router setup needed"],
           ["direct", "Direct — friends connect to your address; the port must be forwarded"]]
_EVENTS = re.compile(r"\[userid:\d+\] player (?P<joined>.+?) connected|\[userid:\d+\] player (?P<left>.+?) disconnected", re.I)

class CoreKeeperGame(SimpleGame):
    reports_answering = False   # who's on comes from its log / admin console, not a port check
    kind = "corekeeper"
    label = "Core Keeper"
    steam_app = 1963720
    exe = EXE
    has_query = False
    kill_signal = "SIGTERM"
    stop_seconds = 45
    install_gb = 1
    requires = ["xvfb-run"]
    ram_note = "about 1-2 GB of memory"
    about = "Underground mining, farming and adventure. Friends can join with a code, no router setup."
    port_layout = [
        {"name": "game", "klass": "game", "start": 27400, "span": 2, "proto": "UDP", "forward": True,
         "label": "Game port (UDP) — only used with “Direct” connections",
         "help": "Forward it and the next port up, only if you choose Direct connections below."},
    ]
    extra_fields = [
        {"name": "connect", "label": "How friends connect", "type": "select", "options": CONNECT,
         "default": "relay"},
        {"name": "worldmode", "label": "World mode", "type": "select", "options": MODES,
         "default": "Normal"},
        {"name": "maxplayers", "label": "Max players (1-100)", "type": "number", "min": 1, "max": 100,
         "default": 8},
        {"name": "seed", "label": "World seed — optional", "placeholder": "leave blank for a random world"},
    ]
    provision_hint = ("Core Keeper — a new world in its own folder. "
                      "With the default “Game ID” connection there is nothing to set up on your router: "
                      "the server's card shows a Game ID for your friends to type in — and anyone who "
                      "has that ID can join, because the game only asks for a password on “Direct” "
                      "connections. With “Direct”, the join password is the shared one, which this "
                      "game limits to 28 characters.")

    def command(self, spec, ports, name, server_dir, install):
        seed = (spec.get("seed") or "").strip()
        if not re.match(r"^[\w \-]{0,40}$", seed):
            raise ActionError("World seed: letters, digits, spaces, - and _ only (up to 40).")
        extra = f' \\\n    -worldseed "{seed}"' if seed else ""
        if self.option(spec, "connect") == "direct":
            extra += f" \\\n    -port {ports['game']}"
        # The server needs a display to start; xvfb-run gives it an invisible one.
        return (f'xvfb-run -a -s "-screen 0 1x1x24 -nolisten tcp" "{install}/{EXE}" -batchmode '
                f'-logfile "{self.log_file(server_dir, install)}" \\\n'
                f'    -datapath "{server_dir}" -world 0 -worldname "{name}" -worldmode {self.option(spec, "worldmode")} \\\n'
                f'    -maxplayers {self.option(spec, "maxplayers")} -password "$GAME_SERVER_PASSWORD"{extra}')

    def pre(self, spec, ports, name, server_dir, install):
        return f'export LD_LIBRARY_PATH="$LD_LIBRARY_PATH:{install}/linux64/"\n'

    def work_dir(self, server_dir, install):
        return server_dir

    def log_file(self, server_dir, install):
        return os.path.join(server_dir, "server.log")

    def proc_pattern(self, spec, ports, server_dir):
        return f"-datapath {server_dir}"

    def provision(self, spec: dict, ports: dict) -> dict:
        out = super().provision(spec, ports)
        if self.option(spec, "connect") != "direct":
            out["join_port"] = None      # friends join with the Game ID, not an address
        return out

    _ids: dict = {}   # log path -> (inode, Game ID) — the line is printed once, at startup

    @classmethod
    def game_id(cls, s) -> str:
        """The Game ID friends type to join (relay connections), read from the
        server's own log. "" for direct connections or before it has started."""
        try:
            ino = os.stat(s.log_path).st_ino
            cached = cls._ids.get(s.log_path)
            if cached and cached[0] == ino:
                return cached[1]
            with open(s.log_path, encoding="utf-8", errors="replace") as f:
                m = re.search(r"Started session with info: (\S+)", f.read(2_000_000))
            if not m:
                return ""
            gid = m.group(1) if re.match(r"^[A-Za-z0-9]{8,40}$", m.group(1)) else ""
            cls._ids[s.log_path] = (ino, gid)
            return gid
        except (OSError, TypeError):
            return ""

    def probe(self, s) -> dict:
        out = empty_probe()
        names = monitor.roster_from_log(s.log_path, _EVENTS) if s.log_path else None
        if names is not None:
            out.update(players=len(names), player_names=names,
                       player_detail=[{"name": n, "id": ""} for n in names])
        gid = self.game_id(s)
        if gid:
            out["note"] = f"Friends join with Game ID: {gid}"
        return out
