"""SCP: Secret Laboratory — a native Linux server, built on games/simple.py (SimpleGame)."""
from __future__ import annotations

import os
import re

from games.base import ActionError, empty_probe
from games.simple import GAME_PORT_HELP, SimpleGame, port


class ScpslGame(SimpleGame):
    kind = "scpsl"
    label = "SCP: Secret Laboratory"
    steam_app = 996560
    exe = "LocalAdmin"
    install_gb = 0.6
    ram_note = "about 2-4 GB of memory"
    about = "Multiplayer horror game set in a containment facility; rounds of escape and pursuit."
    has_query = False
    kill_signal = "SIGTERM"
    stop_seconds = 30            # rounds, not worlds: nothing to save
    console_commands = {"broadcast": "/bc 10 {message}"}
    quit_command = "exit"
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
        return (self.option(spec, "maxplayers"),
                self.option(spec, "friendly_fire"), email)

    def command(self, spec, ports, name, server_dir, install):
        self._options(spec)
        return f'./LocalAdmin {ports["game"]} --acceptEULA --useDefault --noSetCursor'

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
        # the game keeps settings in the user's config folder; give each server its own
        return f'export XDG_CONFIG_HOME="{server_dir}"\n'

    def log_file(self, server_dir, install):
        return os.path.join(server_dir, "server.log")

    def proc_pattern(self, spec, ports, server_dir):
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
        out = empty_probe()
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
        return super().broadcast(s, re.sub(r"[<>]", " ", message))   # no rich-text tags
