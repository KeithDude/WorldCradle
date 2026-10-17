"""Don't Starve Together game type (native Linux dedicated server).

A DST server is a "cluster": the surface world (the Master shard) and,
optionally, the Caves shard — two processes that talk to each other locally.
Setting names below are the ones the server binary reads from cluster.ini and
each shard's server.ini. Player names come from the master shard's log.
"""
from __future__ import annotations

import os
import re
import secrets

import monitor
from games import common
from games.base import ActionError, empty_probe, opt_bool, safe_name
from games.simple import SimpleGame

EXE = "dontstarve_dedicated_server_nullrenderer_x64"
STORAGE_ROOT = "~/.klei"                 # the game's own default location for clusters
CONF_DIR = "DoNotStarveTogether"
GAME_MODES = [["survival", "Survival (the standard game)"],
              ["endless", "Endless (the world never resets when everyone dies)"],
              ["wilderness", "Wilderness (random spawn, no revival)"]]
INTENTIONS = [["cooperative", "Cooperative — working together"],
              ["social", "Social — a place to hang out"],
              ["competitive", "Competitive — players against each other"],
              ["madness", "Madness — anything goes"]]

class DstGame(SimpleGame):
    join_steps = [
        "In Don't Starve Together: <b>Browse Games</b>, search for <b>{server}</b> and join.",
        "If it doesn't show up: open the console with the <b>~</b> key and type "
        "<code>c_connect(\"{host}\", {port}, \"password\")</code> with the join password.",
        "{password}",
    ]
    reports_answering = False   # who's on comes from its log / admin console, not a port check
    kind = "dst"
    label = "Don't Starve Together"
    steam_app = 343050
    exe = "bin64/" + EXE
    run_dir = "bin64"
    has_query = False            # who's on is read from its log
    stop_seconds = 40            # Ctrl-C makes each level save and quit; it can then hang on exit
    install_gb = 5
    ram_note = "about 2-3 GB of memory with caves"
    about = "Co-op wilderness survival. A server is a world, optionally with a caves level."
    # no remote console — admin is done in-game
    # Players connect to each level directly, so both level ports are forwarded.
    # The rest are bound on this computer only and are picked automatically.
    port_layout = [
        {"name": "game", "klass": "game", "start": 10999, "proto": "UDP", "forward": True, "label": "World port (UDP)",
         "help": "The surface world. Forward it."},
        {"name": "caves", "klass": "game", "start": 11000, "proto": "UDP", "forward": True, "label": "Caves port (UDP)",
         "help": "Players are handed to this port when they enter the caves. Forward it too."},
        {"name": "steam_master", "klass": "query", "start": 27050, "label": "Steam port (world)", "form": False},
        {"name": "auth_master", "klass": "query", "start": 8770, "label": "Steam sign-in port (world)", "form": False},
        {"name": "steam_caves", "klass": "query", "start": 27051, "label": "Steam port (caves)", "form": False},
        {"name": "auth_caves", "klass": "query", "start": 8771, "label": "Steam sign-in port (caves)", "form": False},
        {"name": "shard", "klass": "rcon", "start": 10888, "label": "Link between the two levels", "form": False},
    ]
    extra_fields = [
        {"name": "cluster_token", "label": "Klei server token (required)", "placeholder": "pds-g^...",
         "help": "Klei requires a free token for every server. Sign in at accounts.klei.com, open "
                 "Games → Don't Starve Together → Game Servers, add a server and copy its token here."},
        {"name": "description", "label": "Description shown in the server list — optional", "placeholder": ""},
        {"name": "game_mode", "label": "Game mode", "type": "select", "options": GAME_MODES,
         "default": "survival"},
        {"name": "intention", "label": "Play style shown to players", "type": "select",
         "options": INTENTIONS, "default": "cooperative"},
        {"name": "maxplayers", "label": "Max players (1-64)", "type": "number", "min": 1, "max": 64,
         "default": 6},
        {"name": "caves", "label": "Include the Caves level", "type": "checkbox", "default": True,
         "help": "Adds the underground world. Uses roughly twice the memory."},
        {"name": "pvp", "label": "Players can hurt each other (PvP)", "type": "checkbox", "default": False},
        {"name": "pause_when_empty", "label": "Pause the world when nobody is online", "type": "checkbox",
         "default": True},
        {"name": "vote_enabled", "label": "Players can start votes (kick, rollback, regenerate)",
         "type": "checkbox", "default": True},
        {"name": "lan_only", "label": "Home network only (not listed on the internet)", "type": "checkbox",
         "default": False},
    ]
    provision_hint = ("Don't Starve Together — creates a new world with its own save folder and ports. "
                      "The join password is the shared one. You need a free Klei server token (see the "
                      "tip on that box) — without it the server can't go online. World generation "
                      "options (seasons, resources, creatures) use the game's defaults.")

    @staticmethod
    def _ini(sections: dict) -> str:
        return "\n".join(f"[{name}]\n" + "".join(f"{k} = {v}\n" for k, v in body.items())
                         for name, body in sections.items())

    def server_folder(self, install, key):
        # the game's own place for worlds ("clusters"), one per server
        return os.path.join(os.path.expanduser(STORAGE_ROOT), CONF_DIR, "rc_" + key.replace("-", "_"))

    @staticmethod
    def _args(server_dir) -> str:
        return (f'-persistent_storage_root "{os.path.dirname(os.path.dirname(server_dir))}" -conf_dir {CONF_DIR} '
                f"-cluster {os.path.basename(server_dir)}")

    def command(self, spec, ports, name, server_dir, install):
        if not re.match(r"^[\x21-\x7e]{20,300}$", (spec.get("cluster_token") or "").strip()):
            raise ActionError("Paste the Klei server token — it's a long code starting with “pds-”. "
                              "Get one free at accounts.klei.com → Games → Don't Starve Together → "
                              "Game Servers.")
        if self.option(spec, "lan_only"):
            # a home-network-only server refuses to start on any other port
            used = [ports["game"]] + ([ports["caves"]] if self.option(spec, "caves") else [])
            if any(not 10998 <= p <= 11018 for p in used):
                raise ActionError("A home-network-only Don't Starve Together server must use game ports "
                                  "between 10998 and 11018 — pick ports in that range, or untick "
                                  "“Home network only”.")
        self.option(spec, "maxplayers")
        return f"./{EXE} {self._args(server_dir)} -shard Master"

    def pre(self, spec, ports, name, server_dir, install):
        sync = common.password_sync(os.path.join(server_dir, "cluster.ini"), [("cluster_password", "join")],
                                    sep=" = ")
        if not self.option(spec, "caves"):
            return sync
        # The Caves level runs as a second process beside the surface one. A background job
        # ignores Ctrl-C (SIGINT) by default, and SIGINT is how the server is told to save and
        # quit — so the Caves process gets the signal back.
        return sync + (f'(cd "{install}/bin64" && exec env --default-signal=INT ./{EXE} {self._args(server_dir)} '
                       "-shard Caves) &\n")

    def write_files(self, spec, ports, name, server_dir, install):
        caves = self.option(spec, "caves")
        b = lambda field, default: str(opt_bool(spec, field, default)).lower()  # noqa: E731
        cluster_ini = self._ini({
            "GAMEPLAY": {
                "game_mode": self.option(spec, "game_mode"),
                "max_players": self.option(spec, "maxplayers"), "pvp": b("pvp", False),
                "pause_when_empty": b("pause_when_empty", True),
                "vote_enabled": b("vote_enabled", True),
            },
            "NETWORK": {
                "cluster_name": name,
                "cluster_description": safe_name(spec.get("description") or "", 200),
                "cluster_password": "",   # filled in from the shared join password at each start
                "cluster_intention": self.option(spec, "intention"),
                "lan_only_cluster": b("lan_only", False),
                "offline_cluster": "false",
            },
            "MISC": {"console_enabled": "true"},
            "SHARD": {
                "shard_enabled": str(caves).lower(), "bind_ip": "127.0.0.1",
                "master_ip": "127.0.0.1", "master_port": ports["shard"],
                "cluster_key": secrets.token_hex(12),
            },
        })
        shards = {"Master": {"NETWORK": {"server_port": ports["game"]},
                             "SHARD": {"is_master": "true"},
                             "STEAM": {"master_server_port": ports["steam_master"],
                                       "authentication_port": ports["auth_master"]},
                             "ACCOUNT": {"encode_user_path": "true"}}}
        if caves:
            shards["Caves"] = {"NETWORK": {"server_port": ports["caves"]},
                               "SHARD": {"is_master": "false", "name": "Caves"},
                               "STEAM": {"master_server_port": ports["steam_caves"],
                                         "authentication_port": ports["auth_caves"]},
                               "ACCOUNT": {"encode_user_path": "true"}}
        os.chmod(server_dir, 0o700)
        for file, body in (("cluster.ini", cluster_ini), ("cluster_token.txt", (spec.get("cluster_token") or "").strip())):
            common.write_private(os.path.join(server_dir, file), body)  # holds the password/token
        for shard, ini in shards.items():
            os.makedirs(os.path.join(server_dir, shard), exist_ok=True)
            with open(os.path.join(server_dir, shard, "server.ini"), "w", encoding="utf-8") as f:
                f.write(self._ini(ini))
        if caves:  # tells the second level to generate a cave world, not another surface
            with open(os.path.join(server_dir, "Caves", "worldgenoverride.lua"), "w", encoding="utf-8") as f:
                f.write('return {\n    override_enabled = true,\n    preset = "DST_CAVE",\n}\n')

    def log_file(self, server_dir, install):
        return os.path.join(server_dir, "Master", "server_log.txt")

    def proc_pattern(self, spec, ports, server_dir):
        return f"-cluster {os.path.basename(server_dir)} -shard Master"

    def probe(self, s) -> dict:
        out = empty_probe()
        names = monitor.dst_players_from_log(s.log_path) if s.log_path else None
        if names is not None:
            out["players"] = len(names)
            out["player_names"] = names
            out["player_detail"] = [{"name": n, "id": ""} for n in names]
        try:  # the player limit is in the world's settings file
            ini = open(os.path.join(s.save_root, "cluster.ini"), encoding="utf-8").read()
            m = re.search(r"^max_players\s*=\s*(\d+)", ini, re.M)
            out["max_players"] = int(m.group(1)) if m else None
        except OSError:
            pass
        return out
