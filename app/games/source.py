"""Valve Source-engine game types: Counter-Strike 2, Garry's Mod, Left 4 Dead 2, Team Fortress 2.

They share one shape: everything is set on the launch line ("+cvar value"),
the Steam query and the RCON admin console both live on the game port, and
there is no world to save. Each game supplies its own launcher and options.
"""
from __future__ import annotations

import re

import monitor
from games.base import ActionError, empty_probe, opt_choice, opt_int
from games.simple import SimpleGame

# Source servers load Steam's client library from ~/.steam/sdk32 or sdk64; a
# fresh machine doesn't have those links, so the launch script makes them.
_SDK_LINES = """for a in 32 64; do
    d="$HOME/.steam/sdk$a"
    [ -e "$d/steamclient.so" ] && continue
    for c in "$HOME/.local/share/Steam/steamcmd/linux$a/steamclient.so" \\
             "$HOME/.steam/steamcmd/linux$a/steamclient.so" \\
             "$HOME/.local/share/gamedash/steamcmd/linux$a/steamclient.so"; do
        if [ -f "$c" ]; then mkdir -p "$d" && ln -sf "$c" "$d/steamclient.so"; break; fi
    done
done
"""
_TOKEN_RE = re.compile(r"^[A-Fa-f0-9]{32}$")
_TOKEN_FIELD = {
    "name": "gslt", "label": "Steam game-server token — optional, needed to appear in the public server list",
    "placeholder": "32 letters and digits",
    "help": "Free from steamcommunity.com/dev/managegameservers (sign in, enter the game's App ID "
            "shown in this form's description, create). Without one the server still works for "
            "friends who connect by address.",
}


class SourceGame(SimpleGame):
    """Base for the Source games below. Subclasses set the class attributes and
    `launch()` (the command line for one server)."""
    own_folder = False       # nothing to keep: every setting is on the command line
    query_on_game_port = True
    kill_signal = "SIGTERM"
    stop_seconds = 30
    rcon_commands = {"broadcast": "say {message}", "kick": 'kick "{target}"'}
    token_app = 0            # the App ID a game-server token must be created for
    lib_path = ".:bin"       # where the server binary finds its own libraries
    default_map = ""
    maps: list[list[str]] = []
    max_limit = 64
    max_default = 10
    port_layout = [
        {"name": "game", "klass": "game", "start": 27100, "proto": "UDP", "forward": True,
         "label": "Game port (UDP)",
         "help": "The port players connect to; it also answers Steam's server browser. Forward it (UDP)."},
    ]

    def common_fields(self) -> list[dict]:
        return [
            {"name": "map", "label": "Starting map", "type": "select", "options": self.maps,
             "default": self.default_map},
            {"name": "maxplayers", "label": f"Max players (1-{self.max_limit})", "type": "number",
             "min": 1, "max": self.max_limit, "default": self.max_default},
            dict(_TOKEN_FIELD),
        ]

    def launch(self, spec: dict, port: int, name: str, maxp: int, mapname: str) -> str:
        """The command line for one server, without passwords (run from `run_dir`)."""
        raise NotImplementedError

    def command(self, spec, ports, name, server_dir, install):
        maxp = opt_int(spec, "maxplayers", self.max_default, 1, self.max_limit, "Max players")
        mapname = opt_choice(spec, "map", [m for m, _ in self.maps], self.default_map, "Starting map")
        token = (spec.get("gslt") or "").strip()
        if token and not _TOKEN_RE.match(token):
            raise ActionError("The Steam game-server token should be 32 letters and digits.")
        return (self.launch(spec, ports["game"], name, maxp, mapname) + " \\\n"
                '    +sv_password "$GAME_SERVER_PASSWORD" +rcon_password "$GAME_ADMIN_PASSWORD"'
                + (f" \\\n    +sv_setsteamaccount {token}" if token else ""))

    def pre(self, spec, ports, name, server_dir, install):
        return _SDK_LINES + f'export LD_LIBRARY_PATH="{self.lib_path}:$LD_LIBRARY_PATH"\n'

    def proc_pattern(self, spec, ports, server_dir):
        return f"-port {ports['game']} "

    def provision(self, spec: dict, ports: dict) -> dict:
        out = super().provision(spec, ports)
        # its admin console (RCON) is on the game port too
        out.update(rcon_port=ports["game"], rcon_password_ref="GAME_ADMIN_PASSWORD")
        return out

    def probe(self, s) -> dict:
        out = empty_probe()
        info = monitor.a2s_info(s.query_port) if s.query_port else None
        if info is not None:
            names = monitor.a2s_player_names(s.query_port) if info["players"] else []
            out.update(reachable=True, players=info["players"], max_players=info["max_players"],
                       player_names=names, player_detail=[{"name": n, "id": n} for n in names])
            return out
        # Some of these servers don't answer the Steam query at all while idle;
        # the admin console's "status" always does.
        parsed = self.parse_status(self.rcon_send(s, "status") or "")
        if parsed:
            names, limit = parsed
            out.update(reachable=True, players=len(names), max_players=limit, player_names=names,
                       player_detail=[{"name": n, "id": n} for n in names])
        return out

    @staticmethod
    def parse_status(text: str) -> tuple[list[str], int | None] | None:
        """(human player names, player limit) from a Source `status` reply."""
        if "hostname" not in text or "players" not in text:
            return None
        limit = re.search(r"players\s*:.*?\((\d+)(?:/\d+)? max\)", text)
        names = [m.group(1) for m in re.finditer(r'(?m)^#\s*\d+(?:\s+\d+)?\s+"(.*?)"\s+(?!BOT)\S+', text)]
        return names, int(limit.group(1)) if limit else None

    def valid_target(self, target: str) -> bool:
        return bool(re.match(r'^[^\r\n";\x00-\x1f]{1,64}$', target))

    def broadcast(self, s, message: str) -> str:
        return super().broadcast(s, re.sub(r'[\r\n";]', " ", message)[:120])


class Cs2Game(SourceGame):
    kind = "cs2"
    label = "Counter-Strike 2"
    steam_app = 730
    token_app = 730
    exe = "game/bin/linuxsteamrt64/cs2"
    run_dir = "game"
    install_gb = 70
    ram_note = "about 2-4 GB of memory"
    about = "Competitive team shooter. A very large download."
    default_map = "de_dust2"
    maps = [[m, m] for m in ("de_dust2", "de_mirage", "de_inferno", "de_nuke", "de_ancient", "de_anubis",
                             "de_vertigo", "de_overpass", "de_train", "cs_office", "cs_italy")]
    MODES = {"competitive": ("0", "1", "Competitive (5 v 5)"), "casual": ("0", "0", "Casual"),
             "wingman": ("0", "2", "Wingman (2 v 2)"), "deathmatch": ("1", "2", "Deathmatch"),
             "armsrace": ("1", "0", "Arms Race")}
    provision_hint = ("Counter-Strike 2 — everything is set when the server starts; there is no saved "
                      "world. The join and admin passwords are the shared ones. For a game-server "
                      "token, use App ID 730.")

    @property
    def extra_fields(self) -> list[dict]:
        return [{"name": "mode", "label": "Game mode", "type": "select", "default": "competitive",
                 "options": [[k, v[2]] for k, v in self.MODES.items()]}] + self.common_fields()

    def launch(self, spec, port, name, maxp, mapname):
        mode = self.option(spec, "mode")
        gt, gm, _ = self.MODES[mode]
        # Valve's own launcher sets up the library path the server needs
        return (f'./cs2.sh -dedicated -console -usercon -ip 0.0.0.0 -port {port} -maxplayers {maxp} '
                f'+game_type {gt} +game_mode {gm} +map {mapname} +hostname "{name}"')


class GmodGame(SourceGame):
    kind = "gmod"
    label = "Garry's Mod"
    steam_app = 4020
    token_app = 4000
    exe = "srcds_linux"
    install_gb = 7
    max_limit = 128
    max_default = 16
    ram_note = "about 1-2 GB of memory, more with many add-ons"
    about = "Physics sandbox with hundreds of community game modes."
    default_map = "gm_construct"
    maps = [["gm_construct", "gm_construct"], ["gm_flatgrass", "gm_flatgrass"]]
    GAMEMODES = [["sandbox", "Sandbox"], ["terrortown", "Trouble in Terrorist Town"]]
    provision_hint = ("Garry's Mod — everything is set when the server starts. The join and admin "
                      "passwords are the shared ones. Workshop add-ons and other game modes are added "
                      "through the launch script. For a game-server token, use App ID 4000.")

    @property
    def extra_fields(self) -> list[dict]:
        return [{"name": "gamemode", "label": "Game mode", "type": "select", "default": "sandbox",
                 "options": self.GAMEMODES}] + self.common_fields()

    def launch(self, spec, port, name, maxp, mapname):
        gm = self.option(spec, "gamemode")
        return (f'./srcds_linux -game garrysmod -console -ip 0.0.0.0 -port {port} +maxplayers {maxp} '
                    f'+gamemode {gm} +map {mapname} +hostname "\\"{name}\\""')


class L4d2Game(SourceGame):
    kind = "l4d2"
    label = "Left 4 Dead 2"
    steam_app = 222860
    token_app = 550
    exe = "srcds_linux"
    install_gb = 9
    max_limit = 8
    max_default = 4
    ram_note = "about 1 GB of memory"
    about = "Four-player co-op zombie shooter."
    default_map = "c1m1_hotel"
    maps = [["c1m1_hotel", "Dead Center"], ["c2m1_highway", "Dark Carnival"], ["c3m1_plankcountry", "Swamp Fever"],
            ["c4m1_milltown_a", "Hard Rain"], ["c5m1_waterfront", "The Parish"], ["c8m1_apartment", "No Mercy"]]
    MODES = [["coop", "Campaign (co-op)"], ["versus", "Versus"], ["survival", "Survival"], ["realism", "Realism"]]
    provision_hint = ("Left 4 Dead 2 — everything is set when the server starts. The join and admin "
                      "passwords are the shared ones. For a game-server token, use App ID 550.")

    def install(self, install_dir: str, on_progress=None) -> tuple[bool, str]:
        # Steam refuses an anonymous Linux download of this server outright
        # ("Invalid platform"). Fetching the Windows build first and then
        # switching to Linux is the long-standing way round it.
        import steam
        steam.app_update(self.steam_app, install_dir, "windows", on_progress)
        return steam.app_update(self.steam_app, install_dir, "linux", on_progress)

    @property
    def extra_fields(self) -> list[dict]:
        return [{"name": "mode", "label": "Game mode", "type": "select", "default": "coop",
                 "options": self.MODES}] + self.common_fields()

    def launch(self, spec, port, name, maxp, mapname):
        mode = self.option(spec, "mode")
        return (f'./srcds_linux -game left4dead2 -console -ip 0.0.0.0 -port {port} +maxplayers {maxp} '
                    f'+map {mapname} {mode} +hostname "\\"{name}\\""')


class Tf2Game(SourceGame):
    kind = "tf2"
    label = "Team Fortress 2"
    steam_app = 232250
    token_app = 440
    exe = "srcds_linux64"
    lib_path = ".:bin:bin/linux64"
    install_gb = 16
    max_limit = 32      # Valve's supported maximum (more needs an unsupported launch switch)
    max_default = 24
    ram_note = "about 1-2 GB of memory"
    about = "Class-based team shooter. Free to play, so easy for friends to join."
    default_map = "cp_dustbowl"
    maps = [[m, m] for m in ("cp_dustbowl", "ctf_2fort", "pl_badwater", "pl_upward", "cp_granary",
                             "koth_harvest_final", "cp_badlands", "plr_hightower")]
    provision_hint = ("Team Fortress 2 — everything is set when the server starts. The join and admin "
                      "passwords are the shared ones. For a game-server token, use App ID 440.")

    @property
    def extra_fields(self) -> list[dict]:
        return self.common_fields()

    def launch(self, spec, port, name, maxp, mapname):
        return (f'./srcds_linux64 -game tf -console -ip 0.0.0.0 -port {port} +maxplayers {maxp} '
                    f'+map {mapname} +hostname "\\"{name}\\""')
