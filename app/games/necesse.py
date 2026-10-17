"""Necesse — a native Linux server (it ships its own Java), built on games/simple.py.

Everything is a launch argument; each server keeps its world, settings and logs in its own data
folder (-datadir). Admin commands go to the server's console; who is online is read from its output.
"""
from __future__ import annotations

import os
import re

import monitor
from games.base import empty_probe
from games.simple import SimpleGame, port

_EVENTS = re.compile(r'Player \d+ \("(?P<joined>[^"\r\n]+)"\) connected|Player \d+ \("(?P<left>[^"\r\n]+)"\) disconnected')


class NecesseGame(SimpleGame):
    kind = "necesse"
    label = "Necesse"
    steam_app = 1169370
    exe = "Server.jar"
    install_gb = 0.4
    ram_note = "about 1-2 GB of memory"
    about = "Top-down sandbox adventure with settlements. Very light on resources."
    has_query = False
    reports_answering = False   # who's on comes from its log, not a port check
    kill_signal = "SIGTERM"
    console_commands = {"save": "save", "broadcast": "say {message}",
                        "kick": 'kick "{target}"', "ban": 'ban "{target}"'}
    quit_command = "stop"       # saves, then quits

    port_layout = [port("game", 14159, "Game port (UDP)", help="The port players connect to. Forward it (UDP).")]
    extra_fields = [
        {"name": "maxplayers", "label": "Max players (1-250)", "type": "number", "min": 1, "max": 250,
         "default": 10},
        {"name": "pause_empty", "label": "Pause the world when nobody is online", "type": "checkbox",
         "default": True},
    ]
    provision_hint = ("Necesse — a new world in its own folder, created the first time the server "
                      "starts. The join password is the shared one.")

    def command(self, spec, ports, name, server_dir, install):
        world = re.sub(r"[^A-Za-z0-9_]", "_", os.path.basename(server_dir))
        return ("./jre/bin/java -XX:+UseG1GC -XX:MaxGCPauseMillis=50 -jar Server.jar -nogui \\\n"
                f'    -datadir "{server_dir}" -world "{world}" -port {ports["game"]} '
                f'-slots {self.option(spec, "maxplayers")} \\\n'
                f'    -password "$GAME_SERVER_PASSWORD" -pausewhenempty {1 if self.option(spec, "pause_empty") else 0} '
                "-logging 1")

    def proc_pattern(self, key, ports, server_dir):
        return f"-datadir {server_dir}"

    def probe(self, s) -> dict:
        out = empty_probe()
        names = monitor.roster_from_log(s.log_path, _EVENTS) if s.log_path else None
        if names is not None:
            out.update(players=len(names), player_names=names,
                       player_detail=[{"name": n, "id": n} for n in names])
        try:   # the startup line states the player limit
            with open(s.log_path, encoding="utf-8", errors="replace") as f:
                m = re.search(r"with (\d+) slots", f.read(8192))
            out["max_players"] = int(m.group(1)) if m else None
        except OSError:
            pass
        return out

    def valid_target(self, target: str) -> bool:
        return bool(re.match(r'^[^\r\n"\x00-\x1f]{1,40}$', target))
