"""StarRupture — a Windows-only server run through Wine, built on games/winegames.py (WineGame)."""
from __future__ import annotations

import os

from games.simple import port
from games.winegames import WineGame


class StarRuptureGame(WineGame):
    kind = "starrupture"
    label = "StarRupture"
    steam_app = 3809400
    exe = "StarRupture/Binaries/Win64/StarRuptureServerEOS-Win64-Shipping.exe"
    run_dir = ""                 # it looks for DSSettings.txt in the folder it is started from
    needs_install_clone = True   # its session settings and passwords are files beside the program
    install_gb = 20
    ram_note = "about 8-16 GB of memory"
    about = "Co-op base building and survival on a hostile planet (early access). Runs through Wine."
    has_query = False
    port_layout = [port("game", 7777, "Game port (UDP)",
                        help="The port players connect to. Forward it for UDP only — never TCP.")]
    extra_fields = [
        {"name": "autosave", "label": "Autosave every … seconds (60-3600)", "type": "number", "min": 60,
         "max": 3600, "default": 300},
    ]
    provision_note = ("StarRupture keeps its session settings beside its program files, so each server "
                      "gets its own copy of the game (about 20 GB).")
    provision_hint = ("StarRupture — a new session with its own copy of the game (a Windows server, run "
                      "through Wine). The session starts by itself; friends join by this network's "
                      "public address and the game port. ⚠ The shared join password is NOT applied: "
                      "this game stores its passwords in an encrypted form only the game itself can "
                      "write, so the server is open to anyone who has the address. The game's in-game "
                      "“Manage Server” screen is switched off on purpose — it lets anyone on the "
                      "internet take the server over. The dashboard can't show its player count.")

    @staticmethod
    def _session(server_dir):
        return ("rc" + "".join(c for c in os.path.basename(server_dir) if c.isalnum()))[:20]

    def command(self, spec, ports, name, server_dir, install):
        self.option(spec, "autosave")
        # The two RCWeb switches turn off the engine's remote-control web interface, which
        # otherwise answers on the game port with no login at all.
        # -realmcradle=… means nothing to the game; it lets the dashboard tell this server's process apart.
        return ('wine ./StarRupture/Binaries/Win64/StarRuptureServerEOS-Win64-Shipping.exe '
                f'-realmcradle={os.path.basename(server_dir)} -Log '
                f'-Port={ports["game"]} -RCWebControlDisable -RCWebInterfaceDisable')

    def sync_lines(self, spec, ports, name, server_dir, install):
        # DSSettings.txt tells the server which session to run. "Start a new game" must only be
        # set while there is no save yet: left on, it would overwrite the save at every start.
        session = self._session(server_dir)
        interval = self.option(spec, "autosave")
        return (f'python3 - "{install}" "{session}" "{interval}" <<\'SESSION\'\n'
                "import glob, json, os, sys\n"
                "root, session, interval = sys.argv[1:4]\n"
                'saves = sorted(glob.glob(os.path.join(root, "StarRupture", "Saved", "SaveGames", "**", "*.sav"),\n'
                "                         recursive=True), key=os.path.getmtime)\n"
                "d = {\"SessionName\": session, \"SaveGameInterval\": interval,\n"
                "     \"StartNewGame\": \"false\" if saves else \"true\",\n"
                "     \"LoadSavedGame\": \"true\" if saves else \"false\",\n"
                "     \"SaveGameName\": os.path.basename(saves[-1]) if saves else \"AutoSave0.sav\"}\n"
                'json.dump(d, open(os.path.join(root, "DSSettings.txt"), "w", encoding="utf-8"), indent=2)\n'
                "SESSION\n")

    def save_dir(self, server_dir, install):
        return os.path.join(install, "StarRupture", "Saved")

    def log_file(self, server_dir, install):
        return os.path.join(install, "StarRupture", "Saved", "Logs", "StarRupture.log")

    def proc_pattern(self, spec, ports, server_dir):
        return f"-realmcradle={spec['key']} -Log"
