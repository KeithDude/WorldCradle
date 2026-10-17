"""simple.py — a base for dedicated servers that are "one program plus launch
arguments": most Unreal/Unity survival and shooter servers.

A subclass declares the program, its ports and form options, and returns the
command line for one server; this base turns that into a launch script, a
per-server data folder and the dashboard's records. Player numbers come from
the Steam query port unless the subclass says otherwise.
"""
from __future__ import annotations

import os

import config
import monitor
from games import common
from games.base import ActionError, GameType, empty_probe, safe_name


class SimpleGame(GameType):
    provisionable = True
    exe = ""                 # program, relative to the install folder (also the install marker)
    run_dir = ""             # folder to start it from, relative to the install ("" = install root)
    kill_signal = "SIGINT"   # what makes it shut down (most of these save and quit on Ctrl-C)
    stop_seconds = 60
    has_query = True         # answers Steam's A2S query on its "query" port
    pre_lines = ""           # extra shell lines before the launch (exports and the like)
    shell = "/bin/sh"        # what runs the launch script ("/bin/bash" when it needs bash features)
    servers_folder = "gamedash-servers"   # each server's own folder: <install>/<this>/<key>

    # ---- games whose admin commands go to their own console -------------------------------
    # With `console_commands`, the launch script feeds the server's console from a file and
    # sends its output to a log (common.console_*): the Save / Message / Kick / Ban buttons type
    # these lines into it ({message} and {target} are filled in), and stopping types
    # `quit_command` — which saves, then quits — before systemd's own stop signal.
    console_commands: dict[str, str] = {}
    quit_command = ""

    @property
    def install_marker(self) -> str:
        return self.exe

    @property
    def actions(self) -> set[str]:
        """The buttons it gets: what its console can do (a subclass may list its own instead)."""
        return set(self.console_commands)

    # ---- for subclasses ---------------------------------------------------
    def command(self, spec: dict, ports: dict, name: str, server_dir: str, install: str) -> str:
        """The command line that starts one server (no leading `exec`). May use
        $GAME_SERVER_PASSWORD / $GAME_ADMIN_PASSWORD, which the script loads."""
        raise NotImplementedError

    def write_files(self, spec: dict, ports: dict, name: str, server_dir: str, install: str) -> None:
        """Create any settings files the server needs before its first start."""

    def pre(self, spec: dict, ports: dict, name: str, server_dir: str, install: str) -> str:
        """Shell lines to run before the launch (e.g. syncing passwords into a settings file)."""
        return self.pre_lines

    def stop_lines(self, spec: dict, ports: dict, name: str, server_dir: str, install: str) -> str:
        """Shell lines that ask the server to save and quit (run before systemd's
        stop signal). "" = the signal alone is enough."""
        if self.quit_command:
            console = common.console_file(self._log(server_dir, install))
            return f'echo "{self.quit_command}" >> "{console}"\n'
        return ""

    def save_dir(self, server_dir: str, install: str) -> str:
        return server_dir

    def log_file(self, server_dir: str, install: str) -> str:
        return ""

    def proc_pattern(self, key: str, ports: dict, server_dir: str) -> str:
        return server_dir

    def _log(self, server_dir: str, install: str) -> str:
        """Where its output goes: the game's own log, or — for a console game — a log of its own."""
        return self.log_file(server_dir, install) or (
            os.path.join(server_dir, "gamedash-console.log") if self.console_commands else "")

    # ---- shared machinery ---------------------------------------------------
    def provision(self, spec: dict, ports: dict) -> dict:
        install = spec.get("install_dir") or config.install_dir(self.kind)
        if not os.path.exists(os.path.join(install, self.exe)):
            raise ActionError(f"{self.label} isn't installed ({install}).")
        key = spec["key"]
        server_dir = os.path.join(install, self.servers_folder, key)
        if os.path.isdir(server_dir):
            raise ActionError(f"A {self.label} server folder for this key already exists ({server_dir}).")
        name = safe_name((spec.get("name") or key).strip()) or key
        cmd = self.command(spec, ports, name, server_dir, install)   # validates the options first
        os.makedirs(server_dir, exist_ok=True)
        self.write_files(spec, ports, name, server_dir, install)
        log = self._log(server_dir, install)
        if self.console_commands:   # typed into through a file; its output kept in the log
            console = common.console_file(log)
            setup = (common.console_pipe_lines(console) +
                     "# The server's console is fed from the file above, so the dashboard can type\n"
                     "# commands into it.\n")
            launch = f'exec {cmd} \\\n    > "{log}" 2>&1 < <(tail -n0 -F "$CONSOLE")\n'
        else:
            setup, launch = "", f"exec {cmd}\n"
        run = os.path.join(install, f"gamedash-{key}-run.sh")
        with open(run, "w", encoding="utf-8") as f:
            f.write(f"#!{'/bin/bash' if self.console_commands else self.shell}\n"
                    f"# gamedash-managed {self.label} server — generated by provision().\n"
                    f"# This server's own files: {server_dir}\n"
                    f". {config.secrets_path()}\n"
                    + self.pre(spec, ports, name, server_dir, install) + setup +
                    f'cd "{os.path.join(install, self.run_dir)}" || exit 1\n'
                    + launch)
        os.chmod(run, 0o755)
        stop_body = self.stop_lines(spec, ports, name, server_dir, install)
        stop = ""
        if stop_body:
            stop = os.path.join(install, f"gamedash-{key}-stop.sh")
            pattern = self.proc_pattern(key, ports, server_dir)
            with open(stop, "w", encoding="utf-8") as f:
                f.write("#!/bin/sh\n# gamedash-managed graceful stop: ask the server to save and quit, then wait.\n"
                        f". {config.secrets_path()}\n" + stop_body +
                        f"i=0\nwhile [ $i -lt {max(10, self.stop_seconds - 15)} ] && "
                        f"pgrep -f -- '{pattern}' >/dev/null; do sleep 1; i=$((i+1)); done\nexit 0\n")
            os.chmod(stop, 0o755)
        out = {
            "exec_start": run, "working_dir": install,
            "game_port": ports["game"], "query_port": ports.get("query"),
            "rcon_port": ports.get("rcon"),
            "a2s": self.has_query and "query" in ports,
            "proc_match": self.proc_pattern(key, ports, server_dir),
            "server_name": name, "join_port": ports["game"],
            "install_dir": install, "steam_app": self.steam_app,
            "kill_signal": self.kill_signal, "timeout_stop": self.stop_seconds,
            "world": key, "save_root": self.save_dir(server_dir, install),
            "extra_ports": [p for n, p in ports.items() if n not in ("game", "query", "rcon")],
        }
        if stop:
            out["exec_stop"] = stop
        if ports.get("rcon"):
            out["rcon_password_ref"] = "GAME_ADMIN_PASSWORD"
        if log:
            out["log_path"] = log
        return out

    def card_rows(self, s) -> dict:
        if type(self).probe is not SimpleGame.probe:      # the game finds players its own way
            return super().card_rows(s)
        asks = bool(self.has_query and s.query_port)     # everything comes from Steam's query
        return {**super().card_rows(s), "players": asks, "answering": asks}

    # ---- the buttons, for a console game ---------------------------------------------------
    _WHAT = {"save": "Save", "broadcast": "Message", "kick": "Kick", "ban": "Ban"}

    def _console(self, s, action: str, **values) -> str:
        line = self.console_commands[action].format(**values)
        if not common.console_send(s, line):
            raise ActionError(f"{self._WHAT[action]} on {s.name} failed — the server's console isn't available.")
        return "sent"

    def save(self, s) -> str:
        return self._console(s, "save") if "save" in self.console_commands else super().save(s)

    def broadcast(self, s, message: str) -> str:
        if "broadcast" not in self.console_commands:
            return super().broadcast(s, message)
        return self._console(s, "broadcast", message=message[:200])

    def kick(self, s, target: str) -> str:
        return self._console(s, "kick", target=target) if "kick" in self.console_commands else super().kick(s, target)

    def ban(self, s, target: str) -> str:
        return self._console(s, "ban", target=target) if "ban" in self.console_commands else super().ban(s, target)

    def probe(self, s) -> dict:
        out = empty_probe()
        info = monitor.a2s_info(s.query_port) if (self.has_query and s.query_port) else None
        if info is not None:
            names = monitor.a2s_player_names(s.query_port) if info["players"] else []
            out.update(reachable=True, players=info["players"], max_players=info["max_players"],
                       player_names=names, player_detail=[{"name": n, "id": ""} for n in names])
        return out


def port(name: str, start: int, label: str, proto: str = "UDP", forward: bool = True,
         klass: str | None = None, span: int = 1, help: str = "", form: bool = True) -> dict:
    """One port_layout entry, with the usual defaults filled in."""
    d = {"name": name, "klass": klass or ("query" if name == "query" else "rcon" if name == "rcon" else "game"),
         "start": start, "proto": proto, "label": label, "help": help}
    if forward:
        d["forward"] = True
    if span > 1:
        d["span"] = span
    if not form:
        d["form"] = False
    return d


GAME_PORT_HELP = "The port players connect to. Forward it (UDP)."
QUERY_PORT_HELP = "Lists the server in the browser and shows the player count here. Forward it (UDP)."
RCON_PORT_HELP = ("Lets the dashboard control the server (player list, messages, saving). Keep it closed: never "
                  "forward it on your router — anyone who could reach it could take over the server.")
