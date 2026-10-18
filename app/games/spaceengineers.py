"""Space Engineers game type. The dedicated server is Windows-only and runs under Wine.

It is a .NET program, so its Wine environment also needs Microsoft's .NET 4.8
and Visual C++ runtimes; the launch script installs them the
first time (a long one-off step). Each server keeps its settings and world in
its own folder (the server's -path option). Setting names are elements of
SpaceEngineers-Dedicated.cfg. Player numbers come from the Steam query, which
answers on the server port.
"""
from __future__ import annotations

import os
from xml.sax.saxutils import escape

from games import common
from games.base import ActionError, safe_name
from games.winegames import WineGame, win

EXE = "DedicatedServer64/SpaceEngineersDedicated.exe"
WORLDS = [["Star System", "Star System (planets and moons)"], ["Earth Planet", "Earth-like planet"],
          ["Mars Planet", "Mars"], ["Alien Planet", "Alien planet"], ["Home System", "Home System"],
          ["Empty World", "Empty space"]]
MODES = [["Survival", "Survival"], ["Creative", "Creative"]]

# keep the join password in step with the ones set in WorldCradle (the game stores it salted and hashed)
_SYNC = """python3 - "{cfg}" "$GAME_SERVER_PASSWORD" <<'SYNC'
import base64, hashlib, os, re, sys
p, pw = sys.argv[1], sys.argv[2]
salt = os.urandom(16)
digest = hashlib.pbkdf2_hmac("sha1", pw.encode("utf-8"), salt, 10000, 32)
t = open(p, encoding="utf-8").read()
for tag, val in (("ServerPasswordHash", digest), ("ServerPasswordSalt", salt)):
    t = re.sub(r"<%s>[^<]*</%s>|<%s ?/>" % (tag, tag, tag),
               lambda m: "<%s>%s</%s>" % (tag, base64.b64encode(val).decode(), tag), t)
open(p, "w", encoding="utf-8").write(t)
SYNC
"""

_RUNTIMES = """export WINEDLLOVERRIDES=""        # this server needs the .NET runtime (mscoree) left enabled
if [ ! -f "$WINEPREFIX/.worldcradle-runtimes" ]; then
    # One-off, 10-30 minutes: put Microsoft's .NET 4.8 and Visual C++ runtimes into
    # this server's Wine environment. The server refuses to start without them.
    echo "worldcradle: preparing the Wine environment (.NET 4.8 + Visual C++) — this takes a while the first time"
    xvfb-run -a winetricks -q dotnet48 || exit 1
    # the Visual C++ runtime straight from Microsoft (winetricks' copy installed
    # files for the wrong processor type in testing)
    mkdir -p "$WINEPREFIX/drive_c/worldcradle" || exit 1
    curl -fsSL -o "$WINEPREFIX/drive_c/worldcradle/vc_redist.x64.exe" https://aka.ms/vs/17/release/vc_redist.x64.exe || exit 1
    xvfb-run -a wine "$WINEPREFIX/drive_c/worldcradle/vc_redist.x64.exe" /quiet /norestart || exit 1
    wineserver -w
    touch "$WINEPREFIX/.worldcradle-runtimes"
fi
"""

_CFG_TEMPLATE = """<?xml version="1.0"?>
<MyConfigDedicated xmlns:xsd="http://www.w3.org/2001/XMLSchema" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <SessionSettings>
    <GameMode>{mode}</GameMode>
    <MaxPlayers>{maxp}</MaxPlayers>
    <OnlineMode>PUBLIC</OnlineMode>
    <AutoSaveInMinutes>5</AutoSaveInMinutes>
    <EnableSpectator>false</EnableSpectator>
  </SessionSettings>
  <LoadWorld />
  <IP>0.0.0.0</IP>
  <SteamPort>{steam_port}</SteamPort>
  <ServerPort>{port}</ServerPort>
  <AsteroidAmount>4</AsteroidAmount>
  <Administrators />
  <Banned />
  <GroupID>0</GroupID>
  <ServerName>{name}</ServerName>
  <WorldName>{name}</WorldName>
  <PauseGameWhenEmpty>{pause}</PauseGameWhenEmpty>
  <IgnoreLastSession>false</IgnoreLastSession>
  <PremadeCheckpointPath>{world_path}</PremadeCheckpointPath>
  <ServerDescription>{description}</ServerDescription>
  <ServerPasswordHash />
  <ServerPasswordSalt />
  <RemoteApiEnabled>false</RemoteApiEnabled>
</MyConfigDedicated>
"""


class SpaceEngineersGame(WineGame):
    kind = "spaceengineers"
    label = "Space Engineers"
    steam_app = 298740
    requires = ["wine", "xvfb-run", "winetricks", "cabextract", "curl"]   # for the one-off runtime setup
    exe = EXE
    run_dir = "DedicatedServer64"
    install_gb = 9
    ram_note = "about 4-8 GB of memory; grows with what players build"
    about = "Space and planet engineering sandbox. Runs through Wine; its first start is slow."
    query_on_game_port = True
    # no graceful shutdown under Wine — the game autosaves every 5 minutes
    port_layout = [
        {"name": "game", "klass": "game", "start": 27500, "proto": "UDP", "forward": True,
         "label": "Game port (UDP)", "help": "The port players connect to. Forward it (UDP)."},
        {"name": "steam", "klass": "query", "start": 8780, "proto": "UDP", "label": "Steam port",
         "form": False},
    ]
    extra_fields = [
        {"name": "world", "label": "Starting world", "type": "select", "options": WORLDS,
         "default": "Star System"},
        {"name": "mode", "label": "Game mode", "type": "select", "options": MODES, "default": "Survival"},
        {"name": "maxplayers", "label": "Max players (1-16)", "type": "number", "min": 1, "max": 16,
         "default": 4},
        {"name": "pause_empty", "label": "Pause the world when nobody is online", "type": "checkbox",
         "default": True},
        {"name": "description", "label": "Description shown in the server list — optional", "placeholder": ""},
    ]
    provision_hint = ("Space Engineers — a new world in its own folder (a Windows server, run through "
                      "Wine). The join password is the shared one. ⚠ The very first start of each "
                      "Space Engineers server takes 10-30 minutes: it has to install Microsoft's .NET "
                      "and Visual C++ runtimes into its own Wine environment (about 2 GB). The card shows it as running "
                      "during that time; players can join once the log shows “Game ready”.")

    def command(self, spec, ports, name, server_dir, install):
        world = self.option(spec, "world")
        if not os.path.isdir(os.path.join(install, "Content", "CustomWorlds", world)):
            raise ActionError(f"This version of Space Engineers doesn't have the “{world}” starting world.")
        # No -ignorelastsession: with it every start reloads the blank starting world and the saved
        # one is discarded. Without it the server continues the last saved session.
        return f'xvfb-run -a wine ./SpaceEngineersDedicated.exe -console -path "{win(server_dir)}"'

    def write_files(self, spec, ports, name, server_dir, install):
        world = self.option(spec, "world")
        common.write_private(self._cfg(server_dir), _CFG_TEMPLATE.format(
            mode=self.option(spec, "mode"),
            maxp=self.option(spec, "maxplayers"),
            steam_port=ports["steam"], port=ports["game"], name=escape(name),
            # must be a full path: a relative one isn't found from the server's own folder
            world_path=escape("Z:" + os.path.join(install, "Content", "CustomWorlds", world).replace("/", "\\")),
            pause=str(self.option(spec, "pause_empty")).lower(),
            description=escape(safe_name(spec.get("description") or "", 200))))

    def pre(self, spec, ports, name, server_dir, install):
        return _SYNC.format(cfg=self._cfg(server_dir)) + super().pre(spec, ports, name, server_dir, install) + _RUNTIMES

    @staticmethod
    def _cfg(server_dir):
        return os.path.join(server_dir, "SpaceEngineers-Dedicated.cfg")

    def save_dir(self, server_dir, install):
        return os.path.join(server_dir, "Saves")

    def proc_pattern(self, spec, ports, server_dir):
        return f"worldcradle-servers\\{spec['key']}"     # its -path argument
