"""Building blocks shared by several game types' generated launch scripts."""
from __future__ import annotations

import os
import re

# ---- the shared passwords, written into a game's settings at every start ---------------------
# The join and admin passwords are set once in RealmCradle (the secrets file). A game's launch
# script reads them and writes them into the game's own settings file just before it starts, so
# a password changed in RealmCradle reaches every server on its next start. Settings files hold a
# placeholder until then.

# which value an entry gets, as the Python name in the generated script
_PASSWORD = {"join": "join", "admin": "admin", "empty": "''"}


def password_sync(path: str, entries: list[tuple[str, str]], *, sep: str = "=", quoted: bool = False,
                  add_missing: bool = False, section: str = "") -> str:
    """Launch-script lines that set `key<sep>value` lines of a settings file to the shared
    passwords. `entries` = [(key, "join" | "admin" | "empty")] ("empty": no password). The file's
    line endings (and a leading byte-order mark) are kept as they are.
      sep:         what separates key and value — "=", " = " or " "
      quoted:      write key="value"
      add_missing: a key that isn't in the file is added at the end …
      section:     … or, when given (e.g. "[/Script/Game.Settings]"), right after that section's
                   header (the section is added at the end if it's missing too)."""
    pairs = "".join(f"    ({key!r}, {_PASSWORD[which]}),\n" for key, which in entries)
    line = "'%s=\"%s\"' % (key, val)" if quoted else f"key + {sep!r} + val"
    if section:
        missing = (f"        head = {section!r}\n"
                   "        t = (t.replace(head, head + '\\n' + line, 1) if head in t\n"
                   "             else t + '\\n' + head + '\\n' + line + '\\n')\n")
    elif add_missing:
        missing = "        t += line + '\\n'\n"
    else:
        missing = "        pass   # not in the file: left out\n"
    return (f'python3 - "{path}" "$GAME_SERVER_PASSWORD" "$GAME_ADMIN_PASSWORD" <<\'SYNC\'\n'
            "import re, sys\n"
            "p, join, admin = sys.argv[1:4]\n"
            't = open(p, encoding="utf-8", newline="").read()     # keep its line endings\n'
            'bom = "\\ufeff" if t.startswith("\\ufeff") else ""\n'
            "t = t[len(bom):]\n"
            "for key, val in (\n" + pairs + "):\n"
            f"    line = {line}\n"
            f"    pattern = r'(?m)^' + re.escape(key + {sep!r}) + r'[^\\r\\n]*'\n"
            "    if re.search(pattern, t):\n"
            "        t = re.sub(pattern, lambda m: line, t)\n"
            "    else:\n" + missing +
            'open(p, "w", encoding="utf-8", newline="").write(bom + t)\n'
            "SYNC\n")


def json_password_sync(path: str, entries: list[tuple[tuple[str, ...], str]], *, indent=2,
                       extra: str = "") -> str:
    """Launch-script lines that set values in a JSON settings file to the shared passwords.
    `entries` = [(("Rcon", "Password"), "admin"), …] — the path of keys to the value (missing
    objects on the way are created). `extra`: more Python run before the file is written back,
    with the settings as `d` and the passwords as `join` and `admin`."""
    sets = "".join(f"put({list(keys)!r}, {_PASSWORD[which]})\n" for keys, which in entries)
    return (f'python3 - "{path}" "$GAME_SERVER_PASSWORD" "$GAME_ADMIN_PASSWORD" <<\'SYNC\'\n'
            "import json, sys\n"
            "p, join, admin = sys.argv[1:4]\n"
            'd = json.load(open(p, encoding="utf-8-sig"))\n'
            "def put(keys, val):\n"
            "    obj = d\n"
            "    for k in keys[:-1]:\n"
            "        obj = obj.setdefault(k, {})\n"
            "    obj[keys[-1]] = val\n"
            + sets + (extra.rstrip("\n") + "\n" if extra else "") +
            f'json.dump(d, open(p, "w", encoding="utf-8"), indent={indent!r})\n'
            "SYNC\n")


def ini_set(text: str, key: str, value) -> str:
    """Replace `key=...` in an ini-style text (first match), keeping everything else."""
    pat = re.compile(r"(?m)^%s=.*$" % re.escape(key))
    line = f"{key}={value}"
    return pat.sub(lambda m: line, text, count=1) if pat.search(text) else text + line + "\n"


# ---- a server console you can type into --------------------------------------
# Many servers only take admin commands (save, say, quit) on their own console.
# The launch script feeds the console from a plain file; writing a line to that
# file is typing it. `tail -F` follows the file, so no named pipe is needed.

def write_private(path: str, text: str) -> None:
    """Write a settings file only this account can read (0600) — for files that hold, or will be
    given at each start, a password or token. The text is written exactly as given (no line-ending
    changes), and a file that already existed is made private too."""
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
        f.write(text)
    os.chmod(path, 0o600)


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

def rcon_quit_lines(port: int, commands, lenient: bool = False) -> str:
    """Shell lines that send a command (or several, in order) over RCON with the shared admin
    password, using the dashboard's own Python and RCON client — the lenient one for servers
    whose RCON only resembles Valve's (the script must have loaded the secrets file)."""
    import sys
    commands = [commands] if isinstance(commands, str) else list(commands)
    client = "palworld_rcon" if lenient else "source_rcon"
    return (f'"{sys.executable}" - {port} "$GAME_ADMIN_PASSWORD" <<\'STOP\'\n'
            "import sys\n"
            f"sys.path.insert(0, {os.path.dirname(os.path.dirname(os.path.abspath(__file__)))!r})\n"
            "import monitor\n"
            f"for cmd in {commands!r}:\n"
            f"    monitor.{client}(int(sys.argv[1]), sys.argv[2], cmd, timeout=15)\n"
            "STOP\n")




def link_farm(install: str, server_dir: str, own: set[str]) -> None:
    """Fill `server_dir` with links to everything in the shared install except
    the names in `own` (the files/folders that server keeps for itself). Lets a
    game that insists on reading its settings from "its own folder" run several
    servers from one download."""
    os.makedirs(server_dir, exist_ok=True)
    for entry in os.listdir(install):
        if entry in own or entry.startswith("realmcradle-") or entry in ("steamapps", "version.txt"):
            continue
        link = os.path.join(server_dir, entry)
        if not os.path.lexists(link):
            os.symlink(os.path.join(install, entry), link)


def wine_prefix(kind: str, key: str) -> str:
    """Each Wine server gets its own prefix: a shared one shares a single
    wineserver, so stopping one server would take the others down with it."""
    return os.path.expanduser(f"~/.wine-rc-{kind}-{key}")
