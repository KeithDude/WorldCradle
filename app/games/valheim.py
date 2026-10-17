"""Valheim game type. No RCON/A2S — player count comes from the server log."""
from __future__ import annotations

import os
import re

import config
import monitor
from games.base import ActionError, GameType, empty_probe, opt_bool, opt_choice, opt_int, safe_name


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


class ValheimGame(GameType):
    join_steps = [
        "In Valheim: <b>Start → “Join Game” tab → “Join IP”</b>.",
        "Enter: <code>{address}</code>",
        "{password}",
    ]
    reports_answering = False   # who's on comes from its log / admin console, not a port check
    kind = "valheim"
    label = "Valheim"
    install_marker = "valheim_server.x86_64"
    install_gb = 2
    ram_note = "about 2-4 GB of memory"
    about = "Viking survival and building. Light on resources; several worlds can share one install."
    steam_app = 896660
    update_script = "UpdateValheimServer.sh"
    actions: set[str] = set()  # no RCON → no in-app controls

    # provisioning: a new world from the shared install
    provisionable = True
    provision_hint = ("Valheim — spins up a world from your existing install (a new one, or an "
                      "existing world if the name matches). Ports and the launch are generated for "
                      "you; the join password is the shared one. Leave the world modifiers on "
                      "“default” for a standard world.")
    extra_fields = (
        [{"name": "world", "label": "World name (3-20 letters/digits)", "placeholder": "NewWorld"},
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

    def provision(self, spec: dict, ports: dict) -> dict:
        INSTALL = config.install_dir("valheim")
        SECRETS = config.secrets_path()
        if not os.path.isdir(INSTALL):
            raise ActionError(f"Valheim isn't installed ({INSTALL} missing).")
        key = spec["key"]
        world = (spec.get("world") or "").strip()
        if not re.match(r"^[A-Za-z0-9_]{3,20}$", world):
            raise ActionError("World name must be 3-20 letters, digits, or underscores.")
        display = safe_name((spec.get("name") or world).strip()) or world
        gp, qp = ports["game"], ports["query"]
        log = f"gamedash-{key}.log"
        run = os.path.join(INSTALL, f"gamedash-{key}-run.sh")
        # optional custom save dir (-savedir); blank → default worlds_local
        savedir = os.path.expanduser((spec.get("savedir") or "").strip())
        if savedir:
            os.makedirs(savedir, exist_ok=True)
            savedir_arg = f' -savedir "{savedir}"'
        else:
            savedir_arg = ""
        modded = (spec.get("profile") or "vanilla") == "modded"
        # ---- optional launch arguments (only emitted when set) ----
        extra = " -public 1" if self.option(spec, "public") else " -public 0"
        if self.option(spec, "crossplay"):
            # -instanceid keeps PlayFab IDs unique across servers on this box
            extra += f' -crossplay -instanceid "{key}"'
        preset = opt_choice(spec, "preset", PRESETS, "", "World preset")
        if preset:
            extra += f" -preset {preset}"
        for m, vals in MODIFIERS.items():
            v = opt_choice(spec, f"mod_{m}", vals, "", _MOD_LABELS[m])
            if v:
                extra += f" -modifier {m} {v}"
        for k in SETKEYS:
            if opt_bool(spec, f"key_{k}", False):
                extra += f" -setkey {k}"
        for arg, lo, hi, label in (("saveinterval", 60, 86400, "World save interval"),
                                   ("backups", 1, 100, "Backups to keep"),
                                   ("backupshort", 60, 604800, "First backup interval"),
                                   ("backuplong", 60, 2592000, "Later backups interval")):
            n = opt_int(spec, arg, None, lo, hi, label)
            if n is not None:
                extra += f" -{arg} {n}"
        # Modded: the BepInEx doorstop preamble (loads the shared install's
        # BepInEx/plugins). Vanilla: clean launch, no doorstop. Both source the
        # join password set in GameDash and share the launch tail.
        doorstop = (
            "# BepInEx doorstop — loads ./BepInEx/plugins from the shared install.\n"
            "# Add/remove mods there; edit this script for per-world launch tweaks.\n"
            "export DOORSTOP_ENABLED=1\n"
            "export DOORSTOP_TARGET_ASSEMBLY=./BepInEx/core/BepInEx.Preloader.dll\n"
            "export DOORSTOP_CORLIB_OVERRIDE_PATH=./unstripped_corlib\n"
            'export LD_LIBRARY_PATH="./doorstop_libs:$LD_LIBRARY_PATH"\n'
            'export LD_PRELOAD="libdoorstop_x64.so:$LD_PRELOAD"\n'
        ) if modded else ""
        script = (
            "#!/bin/sh\n"
            f"# gamedash-managed Valheim world ({'modded' if modded else 'vanilla'}).\n"
            f". {SECRETS}\n"
            f"{doorstop}"
            "export LD_LIBRARY_PATH=./linux64:$LD_LIBRARY_PATH\n"
            "export SteamAppID=892970\n"
            f'exec ./valheim_server.x86_64 -nographics -batchmode -logfile "./{log}" '
            f'-name "{display}" -port {gp} -world "{world}"{savedir_arg} '
            f'-password "${{GAME_SERVER_PASSWORD}}"{extra}\n'
        )
        with open(run, "w", encoding="utf-8") as f:
            f.write(script)
        os.chmod(run, 0o755)
        return {
            "exec_start": run, "working_dir": INSTALL,
            "game_port": gp, "query_port": qp, "rcon_port": None,
            "a2s": False, "proc_match": f"-port {gp}",
            "server_name": display, "join_port": gp,
            "log_path": os.path.join(INSTALL, log),
            "install_dir": INSTALL, "steam_app": 896660,
            "kill_signal": "SIGINT", "timeout_stop": 60,  # clean Valheim save on stop
            "world": world, "save_root": savedir,  # for backup save_paths
        }
