"""simple.py — a base for dedicated servers that are "one program plus launch
arguments": most Unreal/Unity survival and shooter servers.

A subclass declares the program, its ports and form options, and returns the
command line for one server; this base turns that into a launch script, a
per-server data folder and the dashboard's records. Player numbers come from
the Steam query port unless the subclass says otherwise.
"""
from __future__ import annotations

import os
import re

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
    query_on_game_port = False   # … or on its game port (it has no separate query port)
    pre_lines = ""           # extra shell lines before the launch (exports and the like)
    shell = "/bin/sh"        # what runs the launch script ("/bin/bash" when it needs bash features)
    servers_folder = "worldcradle-servers"   # each server's own folder: <install>/<this>/<key>
    own_folder = True        # False: it keeps nothing of its own (no world), so it gets no folder

    # ---- games whose admin commands go to their own console -------------------------------
    # With `console_commands`, the launch script feeds the server's console from a file and
    # sends its output to a log (common.console_*): the Save / Message / Kick / Ban buttons type
    # these lines into it ({message} and {target} are filled in), and stopping types
    # `quit_command` — which saves, then quits — before systemd's own stop signal.
    console_commands: dict[str, str] = {}
    quit_command = ""
    # The same for a game whose admin commands go over its admin console port (RCON), with the
    # shared admin password: e.g. {"save": "/server-save", "kick": "/kick {target}"}.
    rcon_commands: dict[str, str] = {}
    rcon_lenient = False     # its RCON only resembles Valve's: use the tolerant client (monitor.palworld_rcon)
    rcon_quit_command: str | tuple = ""   # sent over RCON on stop (saves, then quits); several are sent in order
    # … or a command sent over RCON just before systemd's stop signal, for a server that shuts
    # down cleanly on the signal but should save first (stopping then doesn't wait for it to quit)
    rcon_save_before_stop = ""
    stop_only_saves = False  # its stop_lines save but leave the quitting to the stop signal (no wait)
    # The log line that says it has finished shutting down, for a server whose process can't be
    # told apart from other servers' (stopping waits for this line instead of the process).
    stopped_line = ""

    @property
    def install_marker(self) -> str:
        return self.exe

    @property
    def actions(self) -> set[str]:
        """The buttons it gets: what its console or admin console can do (a subclass may list
        its own instead)."""
        return set(self.console_commands) | set(self.rcon_commands)

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
        if self.rcon_quit_command or self.rcon_save_before_stop:
            return common.rcon_quit_lines(ports["rcon"], self.rcon_quit_command or self.rcon_save_before_stop,
                                          self.rcon_lenient)
        return ""

    def after_stop_lines(self, spec: dict, server_dir: str) -> str:
        """Shell lines run once it has quit (or the wait is over), at the end of the stop script."""
        return ""

    def save_dir(self, server_dir: str, install: str) -> str:
        return server_dir

    def server_folder(self, install: str, key: str) -> str:
        """Each server's own folder."""
        return os.path.join(install, self.servers_folder, key)

    def work_dir(self, server_dir: str, install: str) -> str:
        """The folder the server runs in."""
        return os.path.join(install, self.run_dir)

    def log_file(self, server_dir: str, install: str) -> str:
        return ""

    def proc_pattern(self, spec: dict, ports: dict, server_dir: str) -> str:
        """A piece of its command line that only this server's process has (plain text)."""
        return server_dir

    def _log(self, server_dir: str, install: str) -> str:
        """Where its output goes: the game's own log, or — for a console game — a log of its own."""
        return self.log_file(server_dir, install) or (
            os.path.join(server_dir, "worldcradle-console.log") if self.console_commands else "")

    # ---- shared machinery ---------------------------------------------------
    def provision(self, spec: dict, ports: dict) -> dict:
        install = spec.get("install_dir") or config.install_dir(self.kind)
        if not os.path.exists(os.path.join(install, self.exe)):
            raise ActionError(f"{self.label} isn't installed ({install}).")
        key = spec["key"]
        server_dir = self.server_folder(install, key)
        # (adopting an existing server re-makes its launch only: its folder, files and saves stay)
        adopt = bool(spec.get("adopt"))
        if self.own_folder and os.path.isdir(server_dir) and not adopt:
            raise ActionError(f"A {self.label} server folder for this key already exists ({server_dir}).")
        name = safe_name((spec.get("name") or key).strip()) or key
        cmd = self.command(spec, ports, name, server_dir, install)   # validates the options first
        if self.own_folder:
            os.makedirs(server_dir, exist_ok=True)
        if not adopt:
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
        run = os.path.join(install, f"worldcradle-{key}-run.sh")
        with open(run, "w", encoding="utf-8") as f:
            f.write(f"#!{'/bin/bash' if self.console_commands else self.shell}\n"
                    f"# worldcradle-managed {self.label} server — generated by provision().\n"
                    + (f"# This server's own files: {server_dir}\n" if self.own_folder else "") +
                    f". {config.secrets_path()}\n"
                    + self.pre(spec, ports, name, server_dir, install) + setup +
                    f'cd "{self.work_dir(server_dir, install)}" || exit 1\n'
                    + launch)
        os.chmod(run, 0o755)
        stop_body = self.stop_lines(spec, ports, name, server_dir, install)
        stop = ""
        if stop_body:
            stop = os.path.join(install, f"worldcradle-{key}-stop.sh")
            running = (f'! grep -q "{self.stopped_line}" "{log}" 2>/dev/null' if self.stopped_line
                       else f"pgrep -f -- '{_regex(self.proc_pattern(spec, ports, server_dir))}' >/dev/null")
            only_saves = self.stop_only_saves or bool(self.rcon_save_before_stop)
            wait = ("" if only_saves else
                    f"i=0\nwhile [ $i -lt {max(10, self.stop_seconds - 15)} ] && "
                    f"{running}; do sleep 1; i=$((i+1)); done\n")
            with open(stop, "w", encoding="utf-8") as f:
                f.write("#!/bin/sh\n# worldcradle-managed graceful stop: "
                        + ("save, then let systemd's stop signal shut it down.\n" if only_saves
                           else "ask the server to save and quit, then wait.\n") +
                        f". {config.secrets_path()}\n" + stop_body + wait
                        + self.after_stop_lines(spec, server_dir) + "exit 0\n")
            os.chmod(stop, 0o755)
        out = {
            "exec_start": run, "working_dir": install,
            "game_port": ports["game"],
            "query_port": ports["game"] if self.query_on_game_port else ports.get("query"),
            "rcon_port": ports.get("rcon"),
            "a2s": self.has_query and ("query" in ports or self.query_on_game_port),
            "proc_match": self.proc_pattern(spec, ports, server_dir),
            "server_name": name, "join_port": ports["game"],
            "install_dir": install, "steam_app": self.steam_app,
            "kill_signal": self.kill_signal, "timeout_stop": self.stop_seconds,
            "extra_ports": self._extra_ports(ports),
        }
        if self.own_folder:
            out.update(world=key, save_root=self.save_dir(server_dir, install))
        if stop:
            out["exec_stop"] = stop
        if ports.get("rcon"):
            out["rcon_password_ref"] = "GAME_ADMIN_PASSWORD"
        if log:
            out["log_path"] = log
        return out

    def _extra_ports(self, ports: dict) -> list[int]:
        """Every port it uses besides the game, query and admin ports themselves — including the
        rest of a run of ports (a "span"), so Start's in-use check covers them all."""
        out = []
        for p in self.port_layout:
            if p["name"] in ports:
                first = 1 if p["name"] in ("game", "query", "rcon") else 0
                out += [ports[p["name"]] + i for i in range(first, p.get("span", 1))]
        return out

    def card_rows(self, s) -> dict:
        if type(self).probe is not SimpleGame.probe:      # the game finds players its own way
            return super().card_rows(s)
        asks = bool(self.has_query and s.query_port)     # everything comes from Steam's query
        return {**super().card_rows(s), "players": asks, "answering": asks}

    # ---- the buttons, for a console game ---------------------------------------------------
    _WHAT = {"save": "Save", "broadcast": "Message", "kick": "Kick", "ban": "Ban"}

    def _command(self, s, action: str, **values) -> str:
        """Do an action by typing its command into the console, or sending it over RCON."""
        if action in self.console_commands:
            if not common.console_send(s, self.console_commands[action].format(**values)):
                raise ActionError(f"{self._WHAT[action]} on {s.name} failed — the server's console isn't available.")
            return "sent"
        reply = self.rcon_send(s, self.rcon_commands[action].format(**values))
        if reply is None:
            raise ActionError(f"{self._WHAT[action]} on {s.name} failed (the admin console didn't answer).")
        return reply.strip() or "ok"

    def rcon_send(self, s, command: str) -> str | None:
        """Send one command over the admin console; its reply, or None if it didn't answer."""
        client = monitor.palworld_rcon if self.rcon_lenient else monitor.rcon_run
        return client(s.rcon_port, s.rcon_password, command)

    def _has(self, action: str) -> bool:
        return action in self.console_commands or action in self.rcon_commands

    def save(self, s) -> str:
        return self._command(s, "save") if self._has("save") else super().save(s)

    def broadcast(self, s, message: str) -> str:
        if not self._has("broadcast"):
            return super().broadcast(s, message)
        # one line; never starting with "/", so a message can't be taken as a command
        return self._command(s, "broadcast", message=message.replace("\n", " ").lstrip("/")[:200])

    def kick(self, s, target: str) -> str:
        return self._command(s, "kick", target=target) if self._has("kick") else super().kick(s, target)

    def ban(self, s, target: str) -> str:
        return self._command(s, "ban", target=target) if self._has("ban") else super().ban(s, target)

    def probe(self, s) -> dict:
        out = empty_probe()
        info = monitor.a2s_info(s.query_port) if (self.has_query and s.query_port) else None
        if info is not None:
            names = monitor.a2s_player_names(s.query_port) if info["players"] else []
            out.update(reachable=True, players=info["players"], max_players=info["max_players"],
                       player_names=names, player_detail=[{"name": n, "id": ""} for n in names])
        return out


def _regex(text: str) -> str:
    """A plain piece of a command line as a pattern pgrep matches literally (it reads regexes:
    ARK's "?" and a Windows path's "\\" would otherwise mean something else)."""
    return re.sub(r"([\\.\[\](){}*+?|^$])", r"\\\1", text)


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
