"""Palworld game type. Uses the tolerant RCON client (its RCON is non-standard)."""
from __future__ import annotations

import os
import re
import shutil

import config
import monitor
from games.base import empty_probe, opt_float, safe_name
from games.simple import RCON_PORT_HELP, SimpleGame

# Run before each start: put the passwords, name, ports and player limit into the settings
# line, and advertise this network's public IP (the crossplay lobby needs it).
_SYNC = """INI="{ini}"
if [ -f "$INI" ]; then
    python3 - "$INI" "$GAME_ADMIN_PASSWORD" "$GAME_SERVER_PASSWORD" {gp} {rp} {maxp} {name_q} <<'PY'
import re, sys
ini, admin, server, port, rcon, maxp, name = sys.argv[1:8]
t = open(ini, "rb").read().decode("utf-8")
def q(field, val):       # quoted "..." subfield inside OptionSettings
    global t
    t = re.sub(r'(%s=")[^"]*(")' % field, lambda m: m.group(1) + val + m.group(2), t)
def b(field, val):       # bare key=value subfield (number / bool)
    global t
    t = re.sub(r'(%s=)[^,)\\s]*' % field, lambda m: m.group(1) + val, t)
q("AdminPassword", admin); q("ServerPassword", server); q("ServerName", name)
b("PublicPort", port); b("RCONEnabled", "True"); b("RCONPort", rcon)
b("ServerPlayerMaxNum", maxp)
open(ini, "wb").write(t.encode("utf-8"))
PY
fi
# Advertise the reachable public IP (EOS crossplay lobby needs it); refresh each
# launch so a dynamic IP can't break joins; skip silently if lookup fails.
if [ -f "$INI" ]; then
    PUB=""
    for u in https://api.ipify.org https://checkip.amazonaws.com https://ifconfig.me; do
        PUB=$(curl -fsS --max-time 6 "$u" 2>/dev/null | tr -d '[:space:]' || true)
        if echo "$PUB" | grep -qE '^[0-9]+(\\.[0-9]+){{3}}$'; then break; fi
        PUB=""
    done
    if [ -n "$PUB" ]; then
        python3 - "$INI" "$PUB" <<'PY'
import re, sys
ini, ip = sys.argv[1], sys.argv[2]
t = open(ini, "rb").read().decode("utf-8")
t = re.sub(r'(PublicIP=")[^"]*(")', lambda m: m.group(1) + ip + m.group(2), t)
open(ini, "wb").write(t.encode("utf-8"))
PY
    fi
fi
"""

DEATH_PENALTIES = [["None", "Nothing dropped"], ["Item", "Drop items (not equipment)"],
                   ["ItemAndEquipment", "Drop items and equipment"],
                   ["All", "Drop items, equipment and Pals"]]


def set_ini_options(ini: str, quoted: dict, bare: dict) -> None:
    """Rewrite subfields of the single OptionSettings=(...) line in
    PalWorldSettings.ini. `quoted` values are "..." strings, `bare` values are
    numbers / True / False / enum names. Unknown keys are left alone (a key the
    installed build doesn't have is simply not there to replace)."""
    t = open(ini, "rb").read().decode("utf-8")  # binary: keep CRLF exactly
    for k, v in quoted.items():
        t = re.sub(r'(?<![A-Za-z_])(%s=")[^"]*(")' % re.escape(k),
                   lambda m: m.group(1) + v + m.group(2), t)
    for k, v in bare.items():
        t = re.sub(r'(?<![A-Za-z_])(%s=)[^,)\s]*' % re.escape(k),
                   lambda m: m.group(1) + v, t)
    open(ini, "wb").write(t.encode("utf-8"))


class PalworldGame(SimpleGame):
    join_steps = [
        "In Palworld: <b>Join Multiplayer (Co-op) → Community Servers</b>, search <b>{server}</b>.",
        "Or use <b>“Connect to Server”</b> by IP: <code>{address}</code>",
        "{password}",
    ]
    reports_answering = False   # who's on comes from its log / admin console, not a port check
    kind = "palworld"
    label = "Palworld"
    exe = "PalServer.sh"
    own_folder = False           # its settings and world live in its own copy of the game
    has_query = False            # it doesn't answer Steam's query; the admin console lists players
    stop_seconds = 90
    rcon_lenient = True          # its RCON only resembles Valve's
    rcon_commands = {"save": "Save", "broadcast": "Broadcast {message}", "kick": "KickPlayer {target}",
                     "ban": "BanPlayer {target}"}
    rcon_quit_command = ("Save", "Shutdown 1 Stopping")   # the documented save, then shutdown
    install_gb = 5
    ram_note = "about 8-16 GB of memory, growing with players and world age"
    about = "Creature-collecting survival. Each extra server needs its own copy of the game files."
    steam_app = 2394010
    update_script = "UpdatePalworldServer.sh"

    # provisioning: Palworld stores its config + saves inside the install and has
    # no save-dir override, so it can't run two instances from one install — a
    # new instance gets its own cloned install (with a disk pre-flight + confirm).
    needs_install_clone = True
    clone_clear_dirs = ("Pal/Saved/SaveGames", "Pal/Saved/Crashes", "Pal/Saved/Logs")
    extra_fields = [
        {"name": "maxplayers", "label": "Max players (1-32)", "type": "number",
         "min": 1, "max": 32, "default": 10},
        {"name": "description", "label": "Server description — optional", "placeholder": ""},
        {"name": "publiclobby", "label": "List in the public community-server browser",
         "type": "checkbox", "default": False, "help": "Launches with -publiclobby."},
        {"name": "pvp", "label": "PvP (players can damage each other)", "type": "checkbox",
         "default": False},
        {"name": "hardcore", "label": "Hardcore (permadeath)", "type": "checkbox", "default": False},
        {"name": "death_penalty", "label": "Death penalty", "type": "select",
         "options": DEATH_PENALTIES, "default": "Item"},
        {"name": "exp_rate", "label": "XP rate (0.1-20, blank = 1)", "type": "number",
         "min": 0.1, "max": 20, "step": 0.1, "placeholder": "1.0"},
        {"name": "capture_rate", "label": "Pal capture rate (0.5-2, blank = 1)", "type": "number",
         "min": 0.5, "max": 2, "step": 0.1, "placeholder": "1.0"},
    ]
    provision_hint = ("Palworld — a separate server with its own fresh world. Name, ports and the "
                      "shared join/admin passwords are re-applied on every launch; the gameplay "
                      "options here are written once to this server's PalWorldSettings.ini, where "
                      "you can change them (and the many other rates) later.")
    provision_note = ("Palworld can't share an install — this creates a separate copy of the "
                      "install (a few GB) with its own world. You'll be told the disk cost and "
                      "free space before it's created.")

    def save_paths(self, s) -> list[dict]:
        install = s.install_dir or config.install_dir("palworld")
        return [{"path": os.path.join(install, "Pal", "Saved", "SaveGames"), "role": "save"}]

    port_layout = [
        # starts above the game's default (8211) so a server set up by hand keeps that one
        {"name": "game", "klass": "game", "start": 8221, "proto": "UDP", "forward": True, "label": "Game port (UDP)",
         "help": "The port players connect to. Forward it."},
        {"name": "query", "klass": "query", "start": 27019, "label": "Steam query port (UDP)"},
        {"name": "rcon", "klass": "rcon", "start": 25576, "label": "RCON port (TCP)",
         "help": RCON_PORT_HELP},
    ]

    @staticmethod
    def _ini(install):
        return os.path.join(install, "Pal/Saved/Config/LinuxServer/PalWorldSettings.ini")

    def command(self, spec, ports, name, server_dir, install):
        self.option(spec, "maxplayers")
        flags = " -publiclobby" if self.option(spec, "publiclobby") else ""
        return (f"{install}/PalServer.sh \\\n"
                f"    -useperfthreads -NoAsyncLoadingThread -UseMultithreadForDS -port={ports['game']} "
                f"-queryport={ports['query']}{flags}")

    def write_files(self, spec, ports, name, server_dir, install):
        pvp = self.option(spec, "pvp")
        bare = {
            # the game's documentation lists all three for PvP
            "bIsPvP": str(pvp), "bEnablePlayerToPlayerDamage": str(pvp),
            "bEnableDefenseOtherGuildPlayer": str(pvp),
            "bHardcore": str(self.option(spec, "hardcore")),
            "DeathPenalty": self.option(spec, "death_penalty"),
        }
        for field, ini_key, lo, hi, label in (("exp_rate", "ExpRate", 0.1, 20, "XP rate"),
                                              ("capture_rate", "PalCaptureRate", 0.5, 2,
                                               "Pal capture rate")):
            n = opt_float(spec, field, None, lo, hi, label)
            if n is not None:
                bare[ini_key] = f"{n:.6f}"
        quoted = {"ServerDescription": safe_name(spec.get("description") or "", 120)}
        ini = self._ini(install)
        if not os.path.isfile(ini):  # never-run install: start from the shipped defaults
            default = os.path.join(install, "DefaultPalWorldSettings.ini")
            if os.path.isfile(default):
                os.makedirs(os.path.dirname(ini), exist_ok=True)
                shutil.copyfile(default, ini)
        if os.path.isfile(ini):
            set_ini_options(ini, quoted, bare)

    def pre(self, spec, ports, name, server_dir, install):
        return _SYNC.format(ini=self._ini(install), gp=ports["game"], rp=ports["rcon"],
                            maxp=self.option(spec, "maxplayers"),
                            name_q='"' + name + '"')   # name is shell-sanitised by safe_name()

    def proc_pattern(self, spec, ports, server_dir):
        return f"-port={ports['game']} "

    def probe(self, s) -> dict:
        out = empty_probe()
        r = self.rcon_send(s, "ShowPlayers")
        if r is not None:
            e = monitor.parse_palworld_players(r)
            out["players"] = len(e)
            out["player_names"] = [x["name"] for x in e]
            out["player_detail"] = e
        return out

    def broadcast(self, s, message: str) -> str:
        # Palworld's Broadcast splits on spaces; underscores render as spaces.
        return super().broadcast(s, message.replace(" ", "_"))
