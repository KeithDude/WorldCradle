"""Soulmask — a native Linux server, built on games/simple.py (SimpleGame)."""
from __future__ import annotations

import os

from games.simple import GAME_PORT_HELP, QUERY_PORT_HELP, SimpleGame, port


def telnet_lines(port_var: int, lines: list[str]) -> str:
    """Shell lines that type `lines` into a plain-text local console port."""
    payload = "".join(l + "\\r\\n" for l in lines)
    return (f"python3 - {port_var} <<'STOP'\n"
            "import socket, sys, time\n"
            "try:\n"
            '    s = socket.create_connection(("127.0.0.1", int(sys.argv[1])), timeout=5)\n'
            f'    time.sleep(0.5); s.sendall(b"{payload}"); time.sleep(1.5); s.close()\n'
            "except OSError:\n"
            "    pass\n"
            "STOP\n")


class SoulmaskGame(SimpleGame):
    kind = "soulmask"
    label = "Soulmask"
    steam_app = 3017300
    exe = "WS/Binaries/Linux/WSServer-Linux-Shipping"
    needs_install_clone = True   # the world is saved beside the program files
    install_gb = 2.5
    ram_note = "about 8-16 GB of memory"
    about = "Tribal survival and base building with recruitable followers."
    stop_seconds = 260   # saving and closing its database takes a few minutes
    port_layout = [port("game", 8777, "Game port (UDP)", help=GAME_PORT_HELP),
                   port("query", 27190, "Steam query port (UDP)", help=QUERY_PORT_HELP),
                   port("echo", 18888, "Local console port (TCP)", proto="TCP", forward=False, klass="rcon",
                        form=False),
                   port("rcon", 19000, "Admin console port (TCP)", proto="TCP", forward=False, form=False)]
    extra_fields = [
        {"name": "maxplayers", "label": "Max players (1-70)", "type": "number", "min": 1, "max": 70,
         "default": 10},
        {"name": "mode", "label": "Combat", "type": "select", "default": "pve",
         "options": [["pve", "PvE (players vs the world)"], ["pvp", "PvP"]]},
    ]
    provision_note = ("Soulmask saves its world beside its program files, so each server gets its own "
                      "copy of the game (about 2 GB).")
    provision_hint = ("Soulmask — a new world with its own copy of the game. The join and admin passwords "
                      "are the shared ones. The first start takes several minutes while the world loads.")

    def pre(self, spec, ports, name, server_dir, install):
        return f'export LD_LIBRARY_PATH="{install}/linux64:$LD_LIBRARY_PATH"\n'

    def command(self, spec, ports, name, server_dir, install):
        maxp = self.option(spec, "maxplayers")
        mode = self.option(spec, "mode")
        return (f'./WS/Binaries/Linux/WSServer-Linux-Shipping WS Level01_Main -server -log -UTF8Output '
                f'-MULTIHOME=0.0.0.0 -forcepassthrough -Port={ports["game"]} -QueryPort={ports["query"]} '
                f'-EchoPort={ports["echo"]} -SteamServerName="{name}" -MaxPlayers={maxp} -{mode} '
                f'-PSW="$GAME_SERVER_PASSWORD" -adminpsw="$GAME_ADMIN_PASSWORD" -saving=600 -backup=900 '
                # its remote console otherwise opens on a fixed port on every network address
                f'-rconaddr=127.0.0.1 -rconport={ports["rcon"]} -rconpsw="$GAME_ADMIN_PASSWORD"')

    def stop_lines(self, spec, ports, name, server_dir, install):
        return telnet_lines(ports["echo"], ["saveworld 1", "quit 3"])   # save now, then quit in 3 s

    def save_dir(self, server_dir, install):
        return os.path.join(install, "WS", "Saved")

    def proc_pattern(self, spec, ports, server_dir):
        return f"-Port={ports['game']} -QueryPort"
