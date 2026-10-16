"""paths.py — where GameDash keeps its runtime data, separate from the code.

Code lives in the repo (``app/``); runtime data lives in a data root so updating
or shipping the code never touches a user's config/saves/logs. The data root is
``$GAMEDASH_HOME`` if set, else ``~/.config/gamedash``. It holds config.json,
servers.json, the secrets file, certs/ and logs/. Save backups default under
``~/.local/share/gamedash/backups`` (override via the ``backups_dir`` setting).

This module has no dependencies so every other module can import it freely.
"""
from __future__ import annotations

import os

HOME = os.environ.get("GAMEDASH_HOME") or os.path.expanduser("~/.config/gamedash")


def data(*parts: str) -> str:
    return os.path.join(HOME, *parts)


CONFIG_FILE = data("config.json")
SERVERS_FILE = data("servers.json")
SECRETS_FILE = data("secrets.conf")          # default for FRESH installs
CERTS_DIR = data("certs")
LOG_DIR = data("logs")
# setup.sh creates this folder; the "backups_dir" setting overrides it
DEFAULT_BACKUP_ROOT = os.environ.get("GAMEDASH_BACKUPS") or os.path.expanduser("~/.local/share/gamedash/backups")


def ensure_home() -> str:
    """Create the data root (0700, it holds secrets) and return it."""
    os.makedirs(HOME, exist_ok=True)
    try:
        os.chmod(HOME, 0o700)
    except OSError:
        pass
    return HOME
