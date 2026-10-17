"""Valheim game type. No RCON/A2S — player count comes from the server log."""
from __future__ import annotations

import os
import re

import monitor
from games.base import ActionError, empty_probe, opt_bool, opt_choice, opt_int
from games.simple import SimpleGame


# World modifiers, straight from the "Valheim Dedicated Server Manual" shipped
# with the server: -preset <name>, -modifier <name> <value>, -setkey <key>.
PRESETS = ["normal", "casual", "easy", "hard", "hardcore", "immersive", "hammer"]
MODIFIERS = {
    "combat": ["veryeasy", "easy", "hard", "veryhard"],
    "deathpenalty": ["casual", "veryeasy", "easy", "hard", "hardcore"],
    "resources": ["muchless", "less", "more", "muchmore", "most"],
    "raids": ["none", "muchless", "less", "more", "muchmore"],
    "portals": ["casual", "hard", "veryhard"],
}
SETKEYS = {
    "nobuildcost": "No build cost",
    "playerevents": "Player-based raids (events follow each player's progress)",
    "passivemobs": "Passive enemies (attack only when provoked)",
    "nomap": "No map",
}
_MOD_LABELS = {"combat": "Combat", "deathpenalty": "Death penalty", "resources": "Resources",
               "raids": "Raids", "portals": "Portals"}


def _choices(values: list[str], blank: str) -> list[list[str]]:
    return [["", blank]] + [[v, v] for v in values]


class ValheimGame(SimpleGame):
    join_steps = [
        "In Valheim: <b>Start → “Join Game” tab → “Join IP”</b>.",
        "Enter: <code>{address}</code>",
        "{password}",
    ]
    reports_answering = False   # who's on comes from its log / admin console, not a port check
    kind = "valheim"
    label = "Valheim"
    exe = "valheim_server.x86_64"
    # its worlds live in its own save folder (the -savedir option, or the game's default), by name
    own_folder = False
    has_query = False            # who's on is read from its log
    install_gb = 2
    ram_note = "about 2-4 GB of memory"
    about = "Viking survival and building. Light on resources; several worlds can share one install."
    steam_app = 896660
    update_script = "UpdateValheimServer.sh"
    # no admin console: no in-app controls
    provision_hint = ("Valheim — spins up a world from your existing install (a new one, or an "
                      "existing world if the name matches). Ports and the launch are generated for "
                      "you; the join password is the shared one. Leave the world modifiers on "
                      "“default” for a standard world.")
    extra_fields = (
        [{"name": "world", "label": "World name (3-20 letters/digits) — blank = from the server's name",
          "placeholder": "NewWorld", "help": "An existing world of this name is loaded as-is."},
         {"name": "savedir", "label": "Save directory (blank = default worlds_local)",
          "placeholder": "~/valheim-saves/NewWorld"},
         {"name": "public", "label": "List in the public server browser", "type": "checkbox",
          "default": False, "help": "Off = join by IP only (-public 0)."},
         {"name": "crossplay", "label": "Crossplay (Xbox / Game Pass players can join)",
          "type": "checkbox", "default": False,
          "help": "Runs on the PlayFab relay backend (-crossplay); players then can't join by LAN IP."},
         {"name": "preset", "label": "World preset", "type": "select",
          "options": _choices(PRESETS, "default (normal)"),
          "help": "A preset overwrites all modifiers; the individual modifiers below are applied after it."}]
        + [{"name": f"mod_{m}", "label": _MOD_LABELS[m], "type": "select",
            "options": _choices(vals, "default")} for m, vals in MODIFIERS.items()]
        + [{"name": f"key_{k}", "label": label, "type": "checkbox", "default": False}
           for k, label in SETKEYS.items()]
        + [{"name": "saveinterval", "label": "World save interval, seconds (blank = 1800)",
            "type": "number", "min": 60, "max": 86400, "placeholder": "1800"},
           {"name": "backups", "label": "Automatic backups to keep (blank = 4)",
            "type": "number", "min": 1, "max": 100, "placeholder": "4"},
           {"name": "backupshort", "label": "First backup interval, seconds (blank = 7200)",
            "type": "number", "min": 60, "max": 604800, "placeholder": "7200"},
           {"name": "backuplong", "label": "Later backups interval, seconds (blank = 43200)",
            "type": "number", "min": 60, "max": 2592000, "placeholder": "43200"}]
    )
    # vanilla = clean launch; modded = BepInEx doorstop (the shared install's
    # BepInEx/plugins are loaded — manage them, and tweak the launch, via the
    # per-server "Edit launch script" editor).
    mod_profiles = ["vanilla", "modded"]

    port_layout = [
        # leaves the conventional 2456/2457 for the first world
        {"name": "game", "klass": "game", "start": 2460, "span": 2,
         "proto": "UDP", "forward": True, "label": "Game port (UDP)",
         "help": "Valheim also uses the next port up as its query port. Forward both."},
    ]

    def provision_ports(self, used: set[int], use_pool: bool = False,
                        wanted: dict | None = None) -> dict:
        out = super().provision_ports(used, use_pool, wanted)
        out["query"] = out["game"] + 1   # fixed by the game: always game port + 1
        return out

    def save_paths(self, s) -> list[dict]:
        if not s.world:
            return []
        # Worlds live in <savedir>/worlds_local (savedir = -savedir, else the
        # HOME-rooted default). Older provisioned entries stored the folder that
        # holds the world files directly, so check that too.
        root = s.save_root or os.path.expanduser("~/.config/unity3d/IronGate/Valheim")
        candidates = [os.path.join(root, "worlds_local"), root]
        for d in candidates:
            # current format: one folder per world (chunked saves)
            if os.path.isdir(os.path.join(d, s.world)):
                return [{"path": os.path.join(d, s.world), "role": "save"}]
            # legacy format: <world>.db + <world>.fwl
            if os.path.exists(os.path.join(d, s.world + ".db")):
                return [{"path": os.path.join(d, s.world + ext), "role": "save"}
                        for ext in (".db", ".fwl")]
        # nothing on disk yet (world not created) — where the folder will appear
        return [{"path": os.path.join(candidates[0], s.world), "role": "save"}]

    def probe(self, s) -> dict:
        out = empty_probe()
        if s.log_path:
            count, names = monitor.valheim_players_from_log(s.log_path)
            out["players"] = count
            out["player_names"] = names
            out["player_detail"] = [{"name": n, "id": ""} for n in names]
        return out

    @staticmethod
    def _world(spec) -> str:
        world = (spec.get("world") or "").strip()
        if not world:   # from the server's name (or key): letters, digits and _ only
            world = re.sub(r"[^A-Za-z0-9_]", "", (spec.get("name") or spec["key"]).replace(" ", "_").replace("-", "_"))[:20]
            world = world if len(world) >= 3 else "World_" + world
        if not re.match(r"^[A-Za-z0-9_]{3,20}$", world):
            raise ActionError("World name must be 3-20 letters, digits, or underscores.")
        return world

    @staticmethod
    def _savedir(spec) -> str:
        """The -savedir folder ("" = the game's default worlds_local)."""
        return os.path.expanduser((spec.get("savedir") or "").strip())

    def command(self, spec, ports, name, server_dir, install):
        world = self._world(spec)
        savedir = self._savedir(spec)
        args = f' -savedir "{savedir}"' if savedir else ""
        args += " -public 1" if self.option(spec, "public") else " -public 0"
        if self.option(spec, "crossplay"):
            # -instanceid keeps PlayFab IDs unique across servers on this box
            args += f' -crossplay -instanceid "{spec["key"]}"'
        preset = opt_choice(spec, "preset", PRESETS, "", "World preset")
        if preset:
            args += f" -preset {preset}"
        for m, vals in MODIFIERS.items():
            v = opt_choice(spec, f"mod_{m}", vals, "", _MOD_LABELS[m])
            if v:
                args += f" -modifier {m} {v}"
        for k in SETKEYS:
            if opt_bool(spec, f"key_{k}", False):
                args += f" -setkey {k}"
        for arg, lo, hi, label in (("saveinterval", 60, 86400, "World save interval"),
                                   ("backups", 1, 100, "Backups to keep"),
                                   ("backupshort", 60, 604800, "First backup interval"),
                                   ("backuplong", 60, 2592000, "Later backups interval")):
            n = opt_int(spec, arg, None, lo, hi, label)
            if n is not None:
                args += f" -{arg} {n}"
        return (f'./valheim_server.x86_64 -nographics -batchmode -logfile "{self.log_file(server_dir, install)}" '
                f'-name "{name}" -port {ports["game"]} -world "{world}" '
                f'-password "${{GAME_SERVER_PASSWORD}}"{args}')

    def write_files(self, spec, ports, name, server_dir, install):
        if self._savedir(spec):
            os.makedirs(self._savedir(spec), exist_ok=True)

    def pre(self, spec, ports, name, server_dir, install):
        # Modded: the BepInEx doorstop (loads the shared install's BepInEx/plugins). Vanilla: a
        # clean launch.
        doorstop = (
            "# BepInEx doorstop — loads ./BepInEx/plugins from the shared install.\n"
            "# Add/remove mods there; edit this script for per-world launch tweaks.\n"
            "export DOORSTOP_ENABLED=1\n"
            "export DOORSTOP_TARGET_ASSEMBLY=./BepInEx/core/BepInEx.Preloader.dll\n"
            "export DOORSTOP_CORLIB_OVERRIDE_PATH=./unstripped_corlib\n"
            'export LD_LIBRARY_PATH="./doorstop_libs:$LD_LIBRARY_PATH"\n'
            'export LD_PRELOAD="libdoorstop_x64.so:$LD_PRELOAD"\n'
        ) if (spec.get("profile") or "vanilla") == "modded" else ""
        return doorstop + "export LD_LIBRARY_PATH=./linux64:$LD_LIBRARY_PATH\nexport SteamAppID=892970\n"

    def log_file(self, server_dir, install):
        return os.path.join(install, f"gamedash-{os.path.basename(server_dir)}.log")

    def proc_pattern(self, spec, ports, server_dir):
        return f"-port {ports['game']}"

    def provision(self, spec: dict, ports: dict) -> dict:
        out = super().provision(spec, ports)
        # the world is found by name in its save folder (see save_paths)
        out.update(world=self._world(spec), save_root=self._savedir(spec))
        return out
