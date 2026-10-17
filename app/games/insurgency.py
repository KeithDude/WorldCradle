"""Insurgency: Sandstorm — a native Linux server, built on games/simple.py (SimpleGame)."""
from __future__ import annotations

import re

import monitor
from games.base import ActionError
from games.simple import GAME_PORT_HELP, QUERY_PORT_HELP, RCON_PORT_HELP, SimpleGame, port


_TOKEN_RE = re.compile(r"^[A-Fa-f0-9]{32}$")


def _gslt_field(app_id: int) -> dict:
    return {"name": "gslt", "label": "Steam game-server token — optional, needed for the public server list",
            "placeholder": "32 letters and digits",
            "help": f"Free from steamcommunity.com/dev/managegameservers (sign in, App ID {app_id}, create)."}


def _gslt(spec: dict) -> str:
    token = (spec.get("gslt") or "").strip()
    if token and not _TOKEN_RE.match(token):
        raise ActionError("The Steam game-server token should be 32 letters and digits.")
    return token


class InsurgencyGame(SimpleGame):
    kind = "insurgency"
    label = "Insurgency: Sandstorm"
    steam_app = 581330
    kill_signal = "SIGTERM"   # it crashes on Ctrl-C; there is no world to save
    exe = "Insurgency/Binaries/Linux/InsurgencyServer-Linux-Shipping"
    run_dir = "Insurgency/Binaries/Linux"
    install_gb = 5
    ram_note = "about 2-4 GB of memory"
    about = "Tactical team shooter with co-op and versus modes."
    actions = {"broadcast"}
    port_layout = [port("game", 27102, "Game port (UDP)", help=GAME_PORT_HELP),
                   port("query", 27131, "Steam query port (UDP)", help=QUERY_PORT_HELP),
                   port("rcon", 27140, "Admin console port (TCP)", proto="TCP", forward=False,
                        help=RCON_PORT_HELP)]
    SCENARIOS = {
        "coop_hideout": ("Co-op Checkpoint — Hideout", "Town", "Scenario_Hideout_Checkpoint_Security"),
        "coop_farmhouse": ("Co-op Checkpoint — Farmhouse", "Farmhouse", "Scenario_Farmhouse_Checkpoint_Security"),
        "push_refinery": ("Push — Refinery", "Oilfield", "Scenario_Refinery_Push_Security"),
        "firefight_crossing": ("Firefight — Crossing", "Canyon", "Scenario_Crossing_Firefight_West"),
    }
    provision_hint = ("Insurgency: Sandstorm — everything is set when the server starts; there is no saved "
                      "world. The join and admin passwords are the shared ones.")

    @property
    def extra_fields(self) -> list[dict]:
        return [{"name": "scenario", "label": "Starting mode and map", "type": "select",
                 "default": "coop_hideout", "options": [[k, v[0]] for k, v in self.SCENARIOS.items()]},
                {"name": "maxplayers", "label": "Max players (1-28)", "type": "number", "min": 1,
                 "max": 28, "default": 8},
                _gslt_field(581320)]

    def command(self, spec, ports, name, server_dir, install):
        _, mapname, scenario = self.SCENARIOS[self.option(spec, "scenario")]
        maxp = self.option(spec, "maxplayers")
        token = _gslt(spec)
        return (f'./InsurgencyServer-Linux-Shipping "{mapname}?Scenario={scenario}?MaxPlayers={maxp}'
                f'?Password=$GAME_SERVER_PASSWORD" -Port={ports["game"]} -QueryPort={ports["query"]} '
                f'-hostname="{name}" -Rcon -RconPassword="$GAME_ADMIN_PASSWORD" '
                f'-RconListenPort={ports["rcon"]} -log'
                + (f" -GSLTToken={token}" if token else ""))

    def proc_pattern(self, key, ports, server_dir):
        return f"-Port={ports['game']} -QueryPort"

    def broadcast(self, s, message: str) -> str:
        r = monitor.rcon_run(s.rcon_port, s.rcon_password, "say " + message.replace("\n", " ")[:200])
        if r is None:
            raise ActionError(f"Message to {s.name} failed (the admin console didn't answer).")
        return "sent"
