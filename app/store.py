"""store.py — the unified server definition store (servers.json).

Holds server *definitions* as plain data; `registry.py` maps these to Server
objects (resolving password refs from secrets.conf). This is the single place
the dashboard adds/edits servers. `managed` says who owns a server's systemd
unit: "realmcradle" (generated here, removable from the dashboard) or "legacy"
(a hand-made unit RealmCradle only monitors and controls, and never deletes).

Passwords are NOT stored here — entries reference secrets.conf via
`rcon_password_ref` (e.g. "GAME_ADMIN_PASSWORD").
"""
from __future__ import annotations

import json
import os
import tempfile
import threading

import paths

STORE_PATH = paths.SERVERS_FILE
_lock = threading.RLock()  # re-entrant: add/remove/update hold it across load+save


def load() -> list[dict]:
    """Return the list of raw server-definition dicts (empty list on any error)."""
    try:
        with open(STORE_PATH, encoding="utf-8") as f:
            data = json.load(f)
        return data.get("servers", []) if isinstance(data, dict) else []
    except (OSError, ValueError):
        return []


def save(servers: list[dict]) -> None:
    with _lock:
        if os.path.exists(STORE_PATH):
            # never replace a store we can't read with a shorter one built from []
            try:
                with open(STORE_PATH, encoding="utf-8") as f:
                    json.load(f)
            except (OSError, ValueError) as e:
                raise RuntimeError(f"refusing to overwrite unreadable {STORE_PATH}: {e}")
        fd, tmp = tempfile.mkstemp(prefix=".servers-", suffix=".tmp",
                                   dir=os.path.dirname(STORE_PATH))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump({"version": 1, "servers": servers}, f, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, STORE_PATH)
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise


def get(key: str) -> dict | None:
    return next((e for e in load() if e.get("key") == key), None)


def add(entry: dict) -> None:
    with _lock:
        servers = load()
        if any(e.get("key") == entry.get("key") for e in servers):
            raise ValueError(f"server key already exists: {entry.get('key')}")
        servers.append(entry)
        save(servers)


def remove(key: str) -> bool:
    with _lock:
        servers = load()
        kept = [e for e in servers if e.get("key") != key]
        if len(kept) == len(servers):
            return False
        save(kept)
        return True


def replace(key: str, entry: dict) -> bool:
    """Swap one entry for a new one, in place (atomic). Returns False if the key isn't there."""
    with _lock:
        servers = load()
        i = next((n for n, e in enumerate(servers) if e.get("key") == key), None)
        if i is None:
            return False
        servers[i] = entry
        save(servers)
        return True


def update(key: str, **fields) -> bool:
    """Set fields on one entry (atomic). Returns False if the key isn't there."""
    with _lock:
        servers = load()
        hit = False
        for e in servers:
            if e.get("key") == key:
                e.update(fields)
                hit = True
        if hit:
            save(servers)
        return hit
