"""Satisfactory game type. Uses the HTTPS Dedicated Server API."""
from __future__ import annotations

import os
import re

import config
import monitor
import registry
from games.base import ActionError, GameType, opt_bool, opt_int


class SatisfactoryGame(GameType):
    join_steps = [
        "In Satisfactory: <b>Server Manager → “Add Server”</b>.",
        "Enter: <code>{address}</code>",
        "Follow the prompts.",
    ]
    server_stats = True     # tick rate, progress and game time from its HTTPS API
    kind = "satisfactory"
    label = "Satisfactory"
    install_marker = "FactoryServer.sh"
    install_gb = 3
    ram_note = "about 4-8 GB of memory, more for very large factories"
    about = "Factory building. You name the server and set its passwords in-game after first connecting."
    steam_app = 1690800
    update_script = "UpdateSatisfactoryServer.sh"
    actions = {"save"}

    # provisioning: a new instance from the SHARED install. Each instance gets
    # its own ports + its own HOME (so its saves/config live in a private dir),
    # so multiple can run from one install. The one thing that corrupts data is
    # two instances writing the SAME save — hence the note below.
    provisionable = True
    extra_fields = [
        {"name": "maxplayers", "label": "Max players (1-64, game default is 4)", "type": "number",
         "min": 1, "max": 64, "default": 4,
         "help": "Applied with an -ini override of [/Script/Engine.GameSession] MaxPlayers."},
        {"name": "seasonal", "label": "Seasonal events (FICSMAS)", "type": "checkbox",
         "default": True, "help": "Unticked launches with -DisableSeasonalEvents."},
    ]
    provision_hint = ("Satisfactory — a new instance from the shared install with its own ports "
                      "and private save folder. The game has few launch options: the server name, "
                      "admin and player passwords, session, autosave interval and auto-pause are "
                      "all set in-game (Server Manager) after you first connect and claim it.")
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

    def provision(self, spec: dict, ports: dict) -> dict:
        INSTALL = config.install_dir("satisfactory")
        if not os.path.isdir(INSTALL):
            raise ActionError(f"Satisfactory isn't installed ({INSTALL} missing).")
        key = spec["key"]
        session = (spec.get("name") or key).strip()
        maxp = opt_int(spec, "maxplayers", 4, 1, 64, "Max players")
        flags = "" if opt_bool(spec, "seasonal", True) else " -DisableSeasonalEvents"
        gp, reliable = ports["game"], ports["query"]
        # Private HOME → its own ~/.config/Epic/FactoryGame/Saved (isolated saves).
        home = os.path.join(INSTALL, "gamedash-homes", key)
        run = os.path.join(INSTALL, f"gamedash-{key}-run.sh")
        script = (
            "#!/bin/sh\n"
            f'export HOME="{home}"\n'
            f'mkdir -p "$HOME"\n'
            f'cd "{INSTALL}" || exit 1\n'
            f'exec ./FactoryServer.sh -Port={gp} -ReliablePort={reliable} '
            f'-unattended -LOG=gamedash-{key}.log \\\n'
            f"    '-ini:Game:[/Script/Engine.GameSession]:MaxPlayers={maxp}'{flags}\n"
        )
        with open(run, "w", encoding="utf-8") as f:
            f.write(script)
        os.chmod(run, 0o755)
        return {
            "exec_start": run, "working_dir": INSTALL,
            "game_port": gp, "query_port": reliable, "rcon_port": None,
            "a2s": False, "proc_match": f"-Port={gp}",
            "server_name": session, "join_port": gp,
            "install_dir": INSTALL, "steam_app": 1690800,
            "kill_signal": "SIGINT", "timeout_stop": 90,  # clean autosave flush on stop
            # this instance's isolated saves live under its private HOME
            "save_root": os.path.join(home, ".config/Epic/FactoryGame/Saved/SaveGames"),
        }

    def __init__(self):
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
        if tok:
            self._tokens[s.game_port] = tok
        return tok

    def probe(self, s) -> dict:
        out = {"players": None, "player_names": [], "player_detail": [],
               "max_players": None, "reachable": None, "sf": None}
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
        name = state.get("activeSessionName") or "gamedash_save"
        ok, msg = monitor.satisfactory_save(s.game_port, token, name)
        if not ok:
            raise ActionError(f"Save on {s.name} failed: {msg}")
        return f"saved (session '{name}')"
