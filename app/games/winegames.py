"""winegames.py — the base for Windows-only dedicated servers of the "one program plus launch
arguments" kind, run through Wine (each game is in its own file: scum.py, astroneer.py, …).

Builds on games/simple.py: each server gets its own Wine environment (see
common.wine_prefix) and its own data folder, handed to the game as a Windows
path. Wine can't pass a "please save and quit" signal on to these servers, so
stopping one ends it at once (unless the game has a console that can shut it
down, like Astroneer); they all save on their own as they run.
"""
from __future__ import annotations

import os

from games import common
from games.simple import SimpleGame


def win(path: str) -> str:
    """A Linux path as the Windows path Wine shows it at, written for use inside
    double quotes in a launch script."""
    return "Z:" + path.replace("/", "\\\\")


class WineGame(SimpleGame):
    steam_platform = "windows"
    requires = ["wine"]
    stop_seconds = 30

    def sync_lines(self, spec, ports, name, server_dir, install) -> str:
        """Shell lines run before each start (password syncing and the like)."""
        return ""

    def pre(self, spec, ports, name, server_dir, install):
        key = os.path.basename(server_dir)
        return (self.sync_lines(spec, ports, name, server_dir, install)
                + common.wine_env_lines(common.wine_prefix(self.kind, key)))

    def after_stop_lines(self, spec, server_dir):
        # Wine's helper programs outlive the server; close them so the stop doesn't hang on them
        return f'WINEPREFIX="{common.wine_prefix(self.kind, spec["key"])}" wineserver -k 2>/dev/null\n'

    def proc_pattern(self, spec, ports, server_dir):
        return f"gamedash-servers\\{spec['key']}\\"
