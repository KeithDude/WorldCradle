"""Record exactly what each game writes when a server is created — its launch script, settings
files and the server record — so a change to how servers are set up can be checked line by line.

Each game is "installed" as a few stand-in files in a scratch folder (only what its setup reads),
then set up with fixed inputs. Paths, this Python and random values are replaced by placeholders
so the record is the same on every computer.

    venv/bin/python tests/provision_snapshots.py --update    # re-record after an intended change
"""
from __future__ import annotations

import json
import os
import random
import secrets
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SNAPSHOTS = os.path.join(HERE, "provision_snapshots")

# What a real install would have that a game's setup reads, and the form values it needs.
FIXTURES: dict[str, dict] = {
    "ark": {"spec": {"map": "TheIsland_WP"},
            "files": {"ShooterGame/Content/Maps/TheIslandSubMaps/.keep": ""}},
    "asa": {"spec": {"map": "TheIsland_WP"},
            "files": {"ShooterGame/Content/Maps/TheIslandSubMaps/.keep": ""}},
    "bedrock": {"files": {"server.properties": "server-name=Dedicated Server\nserver-port=19132\n"
                                               "server-portv6=19133\nmax-players=10\ngamemode=survival\n"}},
    "dragonwilds": {"spec": {"owner_id": "0123456789abcdef0123456789abcdef"}},
    "dst": {"spec": {"cluster_token": "pds-g^KU_test^" + "x" * 30}},
    "eco": {"files": {"Configs/Network.eco.template": json.dumps(
        {"Description": "", "GameServerPort": 3000, "WebServerPort": 3001, "Password": "",
         "PublicServer": True, "MaxConnections": -1, "Name": ""})}},
    "humanitz": {"files": {"HumanitZServer/REF_GameServerSettings.ini":
                           "ServerName=\"HumanitZ Server\"\nPassword=\"\"\nRCONEnabled=false\n"
                           "RConPort=8888\nRCONPass=\"\"\nMaxPlayers=8\n"}},
    "scpsl": {"files": {"ConfigTemplates/config_gameplay.template.txt":
                        "server_name: My Server Name\nmax_players: 20\n"}},
    "sdtd": {"files": {"serverconfig.xml":
                       '<?xml version="1.0"?>\n<ServerSettings>\n'
                       '  <property name="ServerName" value="My Game Host"/>\n'
                       '  <property name="ServerPort" value="26900"/>\n'
                       '  <property name="ServerPassword" value=""/>\n'
                       '  <property name="ServerMaxPlayerCount" value="8"/>\n'
                       '  <!-- <property name="UserDataFolder" value="absolute path" /> -->\n'
                       '  <property name="TelnetEnabled" value="true"/>\n'
                       '  <property name="TelnetPort" value="8081"/>\n'
                       '  <property name="TelnetPassword" value=""/>\n'
                       '</ServerSettings>\n'}},
    "spaceengineers": {"files": {"Content/CustomWorlds/Star System/Sandbox.sbc": "<MyObjectBuilder_Checkpoint/>"}},
    "squad": {"files": {"SquadGame/ServerConfig/Server.cfg": "ServerName=\"Squad Server\"\nMaxPlayers=100\n",
                        "SquadGame/ServerConfig/Rcon.cfg": "IP=0.0.0.0\nPort=21114\nPassword=\n"}},
    "squad44": {"files": {"PostScriptum/ServerConfig/Server.cfg": "ServerName=\"Server\"\nMaxPlayers=80\n"
                                                                  "ServerPassword=\n",
                          "PostScriptum/ServerConfig/Rcon.cfg": "IP=0.0.0.0\nPort=21114\nPassword=\n"}},
    "valheim": {"spec": {"world": "TestWorld"}},
    "vrising": {"files": {
        "VRisingServer_Data/StreamingAssets/Settings/ServerHostSettings.json": json.dumps(
            {"Name": "V Rising Server", "Description": "", "Port": 9876, "QueryPort": 9877, "MaxConnectedUsers": 40,
             "Password": "", "Rcon": {"Enabled": False, "Port": 25575, "Password": ""}}),
        "VRisingServer_Data/StreamingAssets/Settings/ServerGameSettings.json": json.dumps({"GameModeType": "PvP"}),
        "VRisingServer_Data/StreamingAssets/GameSettingPresets/StandardPvE.json": "{}",
        "VRisingServer_Data/StreamingAssets/GameSettingPresets/StandardPvP.json": "{}"}},
}


def _counter_token(prefix: str):
    n = {"i": 0}

    def token(nbytes=None):
        n["i"] += 1
        return f"{prefix}{n['i']:04d}"
    return token


def record_all() -> dict[str, dict]:
    """{game kind: {"fields": what setup returned, "files": {path: text}}} for every game."""
    root = tempfile.mkdtemp(prefix="gdsnap-")
    sys.path.insert(0, os.path.join(os.path.dirname(HERE), "app"))
    import config
    import games
    home = os.path.join(root, "home")
    os.makedirs(home)
    real_expanduser = os.path.expanduser
    os.path.expanduser = lambda p: home + p[1:] if p.startswith("~") else p
    secrets_file = os.path.join(root, "secrets.conf")
    with open(secrets_file, "w") as f:
        f.write('GAME_SERVER_PASSWORD="joinpw"\nGAME_ADMIN_PASSWORD="adminpw"\n')
    saved = (config.secrets_path, config.install_dir, secrets.token_hex, secrets.token_urlsafe,
             secrets.choice, os.urandom)
    config.secrets_path = lambda: secrets_file
    out = {}
    try:
        for g in sorted(games.all_types(), key=lambda g: g.kind):
            if not g.provisionable or g.kind == "custom":
                continue
            fixture = FIXTURES.get(g.kind, {})
            install = os.path.join(root, "installs", g.kind)
            for rel, text in {**({g.install_marker: ""} if g.install_marker else {}),
                              **fixture.get("files", {})}.items():
                path = os.path.join(install, rel)
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, "w") as f:
                    f.write(text)
            os.makedirs(install, exist_ok=True)
            config.install_dir = lambda kind, install=install: install
            secrets.token_hex = _counter_token("hex")      # random values, made repeatable
            secrets.token_urlsafe = _counter_token("url")
            random.seed(0)
            secrets.choice = random.choice
            os.urandom = lambda n: bytes(range(1, n + 1))
            before = _all_files(root)
            spec = {"key": "test", "name": "Test World", "start": False, "install_dir": install, "eula": True}
            for field in g.extra_fields:
                if field.get("default") is not None:
                    spec[field["name"]] = field["default"]
            spec.update(fixture.get("spec", {}))
            ports = g.provision_ports(set(), False, {})
            try:
                fields = g.provision(spec, ports)
            except Exception as e:   # recorded too: a game that can't be set up is a difference
                fields = {"error": f"{type(e).__name__}: {e}"}
            written = {p: t for p, t in _all_files(root).items() if before.get(p) != t}
            out[g.kind] = {"ports": ports, "fields": fields, "files": written}
            # leave nothing behind for the next game (they share the home folder)
            for p in written:
                os.remove(os.path.join(root, p))
    finally:
        (config.secrets_path, config.install_dir, secrets.token_hex, secrets.token_urlsafe,
         secrets.choice, os.urandom) = saved
        os.path.expanduser = real_expanduser
    return _placeholders(json.loads(json.dumps(out, default=str)), root)


def _placeholders(value, root: str):
    """The scratch folder, this Python and GameDash's own folder, as placeholders — in Linux and in Windows (Wine) form."""
    if isinstance(value, dict):
        return {k: _placeholders(v, root) for k, v in value.items()}
    if isinstance(value, list):
        return [_placeholders(v, root) for v in value]
    if isinstance(value, str):
        win = root.replace("/", "\\")
        return (value.replace(root, "<ROOT>").replace(win.replace("\\", "\\\\"), "<WINROOT>")
                .replace(win, "<WINROOT>").replace(sys.executable, "<PYTHON>")
                .replace(os.path.join(os.path.dirname(HERE), "app"), "<APP>"))
    return value


def _all_files(root: str) -> dict[str, str]:
    files = {}
    for dirpath, _, names in os.walk(root):
        for n in names:
            path = os.path.join(dirpath, n)
            try:
                with open(path, encoding="utf-8", errors="replace") as f:
                    files[os.path.relpath(path, root)] = f.read()
            except OSError:
                pass
    return files


def save(records: dict) -> None:
    os.makedirs(SNAPSHOTS, exist_ok=True)
    for kind, record in records.items():
        with open(os.path.join(SNAPSHOTS, f"{kind}.json"), "w") as f:
            json.dump(record, f, indent=1, sort_keys=True)
            f.write("\n")


if __name__ == "__main__":
    os.environ.setdefault("GAMEDASH_HOME", tempfile.mkdtemp(prefix="gdsnap-home-"))
    os.environ.setdefault("GAMEDASH_QUIET_LOG", "1")
    records = record_all()
    for kind, r in records.items():
        if "error" in r["fields"]:
            print(f"{kind}: {r['fields']['error']}")
    if "--update" in sys.argv:
        save(records)
        print(f"recorded {len(records)} games in {SNAPSHOTS}")
