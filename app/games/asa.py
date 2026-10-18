"""ARK: Survival Ascended game type. Windows-only server, run under Wine.

Works like ARK: Survival Evolved (same RCON console, same launch-line style),
so the player list and the save / message / kick / ban controls are inherited
from that game type. Each map is a server with its own save folder; maps with
the same cluster name share characters.
"""
from __future__ import annotations

from games import common
from games.ark import ArkGame
from games.base import GameType
from games.simple import RCON_PORT_HELP
from games.winegames import WineGame, win

EXE = "ShooterGame/Binaries/Win64/ArkAscendedServer.exe"
MAPS = [["TheIsland_WP", "The Island"], ["ScorchedEarth_WP", "Scorched Earth"],
        ["TheCenter_WP", "The Center"], ["Aberration_WP", "Aberration"],
        ["Extinction_WP", "Extinction"], ["Astraeos_WP", "Astraeos"], ["Ragnarok_WP", "Ragnarok"]]

class AsaGame(ArkGame):
    join_steps = GameType.join_steps     # not ARK's Steam-favourites route
    kind = "asa"
    label = "ARK Ascended"
    title = "ARK: Survival Ascended"
    steam_app = 2430930
    steam_platform = "windows"
    requires = ["wine"]
    update_script = None
    exe = EXE
    run_dir = "ShooterGame/Binaries/Win64"
    has_query = False            # it doesn't answer Steam's query; the admin console lists players
    install_gb = 16
    ram_note = "about 12-16 GB of memory per running map"
    about = "The remake of ARK. Very heavy; the server is Windows-only, so it runs through Wine."

    port_layout = [
        {"name": "game", "klass": "game", "start": 7800, "proto": "UDP", "forward": True,
         "label": "Game port (UDP)", "help": "The port players connect to. Forward it (UDP)."},
        {"name": "rcon", "klass": "rcon", "start": 27045, "proto": "TCP", "label": "Admin console port (TCP)",
         "help": RCON_PORT_HELP},
    ]
    provision_hint = ("ARK: Survival Ascended — adds a map (a Windows server, run through Wine). The join "
                      "and admin passwords are the shared ones; maps with the same cluster name share "
                      "characters and dinos. BattlEye anti-cheat is off because it can't run under "
                      "Wine. Each running map needs a lot of memory, and the first start takes 5-10 "
                      "minutes.")

    @property
    def extra_fields(self) -> list[dict]:
        return [
            {"name": "map", "label": "Map", "type": "select", "options": MAPS, "default": "TheIsland_WP"},
            {"name": "maxplayers", "label": "Max players (1-127)", "type": "number", "min": 1,
             "max": 127, "default": 10},
            {"name": "mode", "label": "Game mode", "type": "select",
             "options": [["pve", "PvE"], ["pvp", "PvP"]], "default": "pve"},
            {"name": "mods", "label": "Mod IDs — optional, comma-separated CurseForge project IDs",
             "placeholder": "928793,900062"},
            {"name": "crossplay", "label": "Allow console players (crossplay)", "type": "checkbox",
             "default": False},
            {"name": "cluster_id", "label": "Cluster name (blank = the configured default)",
             "placeholder": "worldcradle"},
        ]

    def session_name(self, spec, name):
        return name

    def command(self, spec, ports, name, server_dir, install):
        mods = self._mods(spec, r"^\d{3,12}(,\d{3,12})*$", "numbers")
        # The admin password must be the LAST "?" option: this game reads everything after it
        # as part of the password. The port is given both ways: without ?Port= it also opens 7777.
        opts = (f"{self.option(spec, 'map')}?listen?SessionName={name}"
                f"?Port={ports['game']}?RCONEnabled=True?RCONPort={ports['rcon']}?AltSaveDirectoryName={self._save(spec)}"
                f"?ServerPVE={'True' if self.option(spec, 'mode') == 'pve' else 'False'}"
                "?ServerPassword=${GAME_SERVER_PASSWORD}?ServerAdminPassword=${GAME_ADMIN_PASSWORD}")
        # with no -ServerPlatform the game lets every platform in, so "off" has to say PC only
        flags = (f" -mods={mods}" if mods else "") + \
                (" -ServerPlatform=ALL" if self.option(spec, "crossplay") else " -ServerPlatform=PC")
        return (f'wine ./ArkAscendedServer.exe \\\n    "{opts}" \\\n'
                f'    -port={ports["game"]} -WinLiveMaxPlayers={self.option(spec, "maxplayers")} -NoBattlEye -server -log \\\n'
                f'    -clusterid={self._cluster_id(spec)} -ClusterDirOverride="{win(self.cluster_dir(install))}"{flags}')

    def pre(self, spec, ports, name, server_dir, install):
        return (f'mkdir -p "{self.cluster_dir(install)}"\n'
                + common.wine_env_lines(common.wine_prefix(self.kind, spec["key"])))

    # The world is saved before the exit command returns; Wine's helper programs linger after
    # the game closes, so they are closed too.
    after_stop_lines = WineGame.after_stop_lines
