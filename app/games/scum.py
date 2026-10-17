"""SCUM — a Windows-only server run through Wine, built on games/winegames.py (WineGame)."""
from __future__ import annotations

import os

from games import common
from games.base import ActionError, safe_name
from games.simple import port
from games.winegames import WineGame, win


class ScumGame(WineGame):
    kind = "scum"
    label = "SCUM"
    steam_app = 3792580
    exe = "SCUM/Binaries/Win64/SCUMServer.exe"
    run_dir = "SCUM/Binaries/Win64"
    install_gb = 15
    ram_note = "about 10-16 GB of memory"
    about = "Hardcore open-world prison-island survival. Runs through Wine; slow to start."
    has_query = False
    port_layout = [port("game", 7042, "Game port (UDP, plus the next two)", span=3,
                        help="The port players connect to. Forward it and the two after it (UDP).")]
    extra_fields = [
        {"name": "maxplayers", "label": "Max players (1-64)", "type": "number", "min": 1, "max": 64,
         "default": 16},
        {"name": "mode", "label": "Play style", "type": "select", "default": "PVE",
         "options": [["PVE", "PvE (players vs the world)"], ["PVP", "PvP"]]},
        {"name": "welcome", "label": "Welcome message — optional", "placeholder": ""},
    ]
    provision_hint = ("SCUM — a new world in its own folder (a Windows server, run through Wine). The "
                      "join password is the shared one. ⚠ Every start is slow: about 20 minutes the "
                      "first time and 10 after that, during which the card shows it as running but "
                      "nobody can join yet. BattlEye anti-cheat is off because it can't run under Wine. "
                      "Admins are the Steam IDs listed in the server's AdminUsers.ini; the dashboard "
                      "can't show its player count. If a friend adds the server by address and the "
                      "game port doesn't work, have them try the game port plus 2 — the community "
                      "guide says that is the port to type.")

    def _ini(self, server_dir):
        return os.path.join(server_dir, "Saved", "Config", "WindowsServer", "ServerSettings.ini")

    def command(self, spec, ports, name, server_dir, install):
        maxp = self.option(spec, "maxplayers")
        self.option(spec, "mode")
        # -noheartbeatthread: under Wine the long map load trips the engine's "hang" watchdog, which kills it
        return (f'wine ./SCUMServer.exe -log -port={ports["game"]} -MaxPlayers={maxp} -nobattleye '
                f'-noheartbeatthread -userdir="{win(server_dir)}\\\\"')

    def write_files(self, spec, ports, name, server_dir, install):
        # The server throws away a settings file that doesn't list every setting,
        # so start from its complete default file (games/data) and change ours.
        import re
        src = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "scum_ServerSettings.ini")
        text = open(src, encoding="utf-8", newline="").read()
        for key, value in (
            ("scum.ServerName", name), ("scum.ServerPassword", "set-at-launch"),
            ("scum.MaxPlayers", self.option(spec, "maxplayers")),
            ("scum.ServerPlaystyle", self.option(spec, "mode")),
            ("scum.WelcomeMessage", safe_name(spec.get("welcome") or "", 200) or "Welcome!"),
        ):
            text, n = re.subn(r"(?m)^%s=[^\r\n]*" % re.escape(key), lambda m: f"{key}={value}", text)
            if n != 1:
                raise ActionError(f"SCUM's settings template is missing {key}.")
        os.makedirs(os.path.dirname(self._ini(server_dir)), exist_ok=True)
        common.write_private(self._ini(server_dir), text)

    def sync_lines(self, spec, ports, name, server_dir, install):
        return common.password_sync(self._ini(server_dir), [("scum.ServerPassword", "join")])

    def save_dir(self, server_dir, install):
        return os.path.join(server_dir, "Saved")

    def log_file(self, server_dir, install):
        return os.path.join(server_dir, "Saved", "Logs", "SCUM.log")
