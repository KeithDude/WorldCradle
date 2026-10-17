"""Custom game type — a user-defined service for games we don't explicitly
support. Monitoring is generic: systemd up/down + process resources (handled by
the poller), plus optional Steam A2S if a query port was configured. No
game-specific controls beyond start/stop/restart (which are systemd-generic)."""
from __future__ import annotations

import monitor
from games.base import GameType


class CustomGame(GameType):
    kind = "custom"
    label = "Custom service"
    actions: set[str] = set()  # no game-specific RCON controls by default

    def card_rows(self, s) -> dict:
        asks = bool(s.query_port)     # only if the owner gave a Steam query port
        return {**super().card_rows(s), "players": asks, "answering": asks}

    def probe(self, s) -> dict:
        out = {"players": None, "player_names": [], "player_detail": [],
               "max_players": None, "reachable": None}
        if s.query_port:  # optional A2S probe if the user gave a query port
            info = monitor.a2s_info(s.query_port)
            if info is not None:
                out["reachable"] = True
                out["players"] = info["players"]
                out["max_players"] = info["max_players"]
        return out
