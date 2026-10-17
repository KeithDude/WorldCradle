"""Satisfactory game type. Uses the HTTPS Dedicated Server API."""
from __future__ import annotations

import os
import re

import config
import monitor
import registry
from applog import app_log
from games.base import ActionError, empty_probe
from games.simple import SimpleGame


class SatisfactoryGame(SimpleGame):
    join_steps = [
        "In Satisfactory: <b>Server Manager → “Add Server”</b>.",
        "Enter: <code>{address}</code>",
        "Follow the prompts.",
    ]
    server_stats = True     # tick rate, progress and game time from its HTTPS API
    kind = "satisfactory"
    label = "Satisfactory"
    exe = "FactoryServer.sh"
    # Each server runs with its own HOME (this folder), so its saves and settings are its own and
    # several can run from one install.
    servers_folder = "realmcradle-homes"
    has_query = False            # players and stats come from its HTTPS API
    stop_seconds = 90
    stop_only_saves = True       # saved through its admin API first: SIGINT alone doesn't save
    install_gb = 3
    ram_note = "about 4-8 GB of memory, more for very large factories"
    about = "Factory building. Start the game itself from the in-game Server Manager after first connecting."
    steam_app = 1690800
    update_script = "UpdateSatisfactoryServer.sh"
    actions = {"save"}           # through its HTTPS API
    extra_fields = [
        {"name": "maxplayers", "label": "Max players (1-64, game default is 4)", "type": "number",
         "min": 1, "max": 64, "default": 4,
         "help": "Applied with an -ini override of [/Script/Engine.GameSession] MaxPlayers."},
        {"name": "seasonal", "label": "Seasonal events (FICSMAS)", "type": "checkbox",
         "default": True, "help": "Unticked launches with -DisableSeasonalEvents."},
    ]
    provision_hint = ("Satisfactory — a new instance from the shared install with its own ports "
                      "and private save folder. Once it is running, RealmCradle claims it for you: it "
                      "gets this server's name and the shared admin and join passwords. Start a new "
                      "game or load a save in-game (Server Manager); the autosave interval and "
                      "auto-pause are set there too.")
    provision_note = ("Never load the SAME save file on two running instances — both would write "
                      "to it at once and corrupt it. It needs both its ports forwarded (game "
                      "UDP+TCP and reliable TCP).")

    # -Port (game/query/API) and -ReliablePort. Both must be forwarded, so both
    # draw from the "game" class; the reliable port is stored as query_port
    # (matching the existing server's convention).
    port_layout = [
        # starts above the game's defaults (7777, and 8888 for its reliable port) so a server set up by hand keeps them
        {"name": "game", "klass": "game", "start": 7779, "proto": "UDP and TCP", "forward": True, "label": "Game port (UDP + TCP)",
         "help": "Game traffic, server query and the HTTPS API. Forward both UDP and TCP."},
        {"name": "query", "klass": "game", "start": 8889, "proto": "TCP", "forward": True, "label": "Reliable messaging port (TCP)",
         "help": "Without this one forwarded, players hang on the loading screen."},
    ]

    def command(self, spec, ports, name, server_dir, install):
        flags = "" if self.option(spec, "seasonal") else " -DisableSeasonalEvents"
        return (f'./FactoryServer.sh -Port={ports["game"]} -ReliablePort={ports["query"]} '
                f'-unattended -LOG=realmcradle-{spec["key"]}.log \\\n'
                f"    '-ini:Game:[/Script/Engine.GameSession]:MaxPlayers={self.option(spec, 'maxplayers')}'{flags}")

    def stop_lines(self, spec, ports, name, server_dir, install):
        # the same save as the dashboard's Save button, into the running session's save
        import sys
        return (f'"{sys.executable}" - {ports["game"]} "$GAME_ADMIN_PASSWORD" <<\'SAVE\'\n'
                "import sys\n"
                f"sys.path.insert(0, {os.path.dirname(os.path.dirname(os.path.abspath(__file__)))!r})\n"
                "import config, monitor\n"
                "port = int(sys.argv[1])\n"
                "token = config.load().get('satisfactory_api_token') or monitor.satisfactory_login(port, sys.argv[2])\n"
                "if token:\n"
                "    state = monitor.satisfactory_state(port, token) or {}\n"
                "    monitor.satisfactory_save(port, token, state.get('activeSessionName') or 'realmcradle_save')\n"
                "SAVE\n")

    def pre(self, spec, ports, name, server_dir, install):
        return f'export HOME="{server_dir}"\n'

    def save_dir(self, server_dir, install):
        return os.path.join(server_dir, ".config/Epic/FactoryGame/Saved/SaveGames")

    def proc_pattern(self, spec, ports, server_dir):
        return f"-Port={ports['game']} "

    def __init__(self):
        super().__init__()
        # minted tokens cached per game_port (each instance has its own API).
        self._tokens: dict[int, str] = {}

    def _get_token(self, s) -> str | None:
        cfg = config.load()
        if cfg.get("satisfactory_api_token"):
            return cfg["satisfactory_api_token"]
        tok = self._tokens.get(s.game_port)
        if tok:
            return tok
        pw = registry.game_admin_password()
        tok = monitor.satisfactory_login(s.game_port, pw) if pw else None
        if not tok and pw:
            # a new server nobody has claimed yet: claim it with the shared passwords, so its
            # owner doesn't have to do it in the game before the dashboard can see it
            tok = monitor.satisfactory_claim(s.game_port, s.server_name or s.name, pw,
                                             registry.load_secrets().get("GAME_SERVER_PASSWORD", ""))
            if tok:
                app_log.info("claimed the new Satisfactory server %s with the shared passwords", s.key)
        if tok:
            self._tokens[s.game_port] = tok
        return tok

    def probe(self, s) -> dict:
        out = empty_probe(sf=None)
        out["reachable"] = monitor.satisfactory_health(s.game_port)
        token = self._get_token(s)
        if token:
            state = monitor.satisfactory_state(s.game_port, token)
            if state is not None:
                out["players"] = state.get("numConnectedPlayers")
                out["max_players"] = state.get("playerLimit")
                phase = re.search(r"Phase_(\d+)", state.get("gamePhase") or "")
                out["sf"] = {
                    "tick": round(state.get("averageTickRate") or 0, 1),
                    "paused": state.get("isGamePaused"),
                    "tier": state.get("techTier"),
                    "phase": int(phase.group(1)) if phase else None,
                    "uptime_s": state.get("totalGameDuration"),
                    "session": state.get("activeSessionName"),
                }
            else:
                self._tokens.pop(s.game_port, None)  # likely stale → re-mint next time
        return out

    def save(self, s) -> str:
        token = self._get_token(s)
        if not token:
            raise ActionError(f"{s.name}: no API token/password configured.")
        state = monitor.satisfactory_state(s.game_port, token) or {}
        name = state.get("activeSessionName") or "realmcradle_save"
        ok, msg = monitor.satisfactory_save(s.game_port, token, name)
        if not ok:
            raise ActionError(f"Save on {s.name} failed: {msg}")
        return f"saved (session '{name}')"
