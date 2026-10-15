"""Building blocks shared by several game types' generated launch scripts."""
from __future__ import annotations

import os
import time

# ---- a server console you can type into --------------------------------------
# Many servers only take admin commands (save, say, quit) on their own console.
# The launch script feeds the console from a plain file; writing a line to that
# file is typing it. `tail -F` follows the file, so no named pipe is needed.

def console_file(log_path: str) -> str:
    return log_path + ".console"


def console_pipe_lines(console: str) -> str:
    """Shell lines to put before the server command; then run it as
    `tail -n0 -F "$CONSOLE" | <server command>`."""
    return f'CONSOLE="{console}"\n: > "$CONSOLE"\n'


def console_send(s, line: str) -> bool:
    """Type one line into a running server's console. False if it has none."""
    if not s.log_path:
        return False
    path = console_file(s.log_path)
    if not os.path.exists(path):
        return False
    with open(path, "a", encoding="utf-8") as f:
        f.write(line.replace("\n", " ").replace("\r", " ") + "\n")
    return True


def stop_script(path: str, console: str, quit_line: str, proc_match: str, wait: int = 45) -> None:
    """Write an ExecStop script: type the game's quit command, then wait for
    the server process to finish saving and exit."""
    with open(path, "w", encoding="utf-8") as f:
        f.write("#!/bin/sh\n"
                "# gamedash-managed graceful stop: ask the server to save and quit, then wait.\n"
                f'echo "{quit_line}" >> "{console}"\n'
                f"i=0\nwhile [ $i -lt {wait} ] && pgrep -f -- '{proc_match}' >/dev/null; do sleep 1; i=$((i+1)); done\n"
                "exit 0\n")
    os.chmod(path, 0o755)


# ---- Windows-only servers under Wine -----------------------------------------

def wine_env_lines(prefix: str) -> str:
    """Shell lines that make Wine run a server headless in its own prefix."""
    return (f'export WINEPREFIX="{prefix}"\n'
            "export WINEDEBUG=-all\n"
            'export WINEDLLOVERRIDES="mscoree,mshtml="   # no Mono/Gecko install prompts (headless)\n'
            "# Run headless: Wine would otherwise open a console window on the desktop\n"
            "# session (unsetting DISPLAY alone isn't enough — it falls back to Wayland).\n"
            "unset DISPLAY\n"
            "export WAYLAND_DISPLAY=wayland-none\n")


# ---- graceful stop over Source RCON -------------------------------------------

def rcon_stop_script(path: str, secrets_path: str, port: int, command: str, proc_match: str,
                     wait: int = 60) -> None:
    """Write an ExecStop script: send the game's quit command over RCON (using
    the dashboard's own Python and RCON client), then wait for the
    server process to finish saving and exit."""
    import sys
    with open(path, "w", encoding="utf-8") as f:
        f.write("#!/bin/sh\n"
                "# gamedash-managed graceful stop: ask the server (over its admin console) to save and quit.\n"
                f". {secrets_path}\n"
                f'"{sys.executable}" - {port} "$GAME_ADMIN_PASSWORD" <<\'STOP\'\n'
                "import sys\n"
                f"sys.path.insert(0, {os.path.dirname(os.path.dirname(os.path.abspath(__file__)))!r})\n"
                "import monitor\n"
                f"monitor.source_rcon(int(sys.argv[1]), sys.argv[2], {command!r}, timeout=8)\n"
                "STOP\n"
                f"i=0\nwhile [ $i -lt {wait} ] && pgrep -f -- '{proc_match}' >/dev/null; do sleep 1; i=$((i+1)); done\n"
                "exit 0\n")
    os.chmod(path, 0o755)


def link_farm(install: str, server_dir: str, own: set[str]) -> None:
    """Fill `server_dir` with links to everything in the shared install except
    the names in `own` (the files/folders that server keeps for itself). Lets a
    game that insists on reading its settings from "its own folder" run several
    servers from one download."""
    os.makedirs(server_dir, exist_ok=True)
    for entry in os.listdir(install):
        if entry in own or entry.startswith("gamedash-") or entry in ("steamapps", "version.txt"):
            continue
        link = os.path.join(server_dir, entry)
        if not os.path.lexists(link):
            os.symlink(os.path.join(install, entry), link)


def wine_prefix(kind: str, key: str) -> str:
    """Each Wine server gets its own prefix: a shared one shares a single
    wineserver, so stopping one server would take the others down with it."""
    return os.path.expanduser(f"~/.wine-gd-{kind}-{key}")
