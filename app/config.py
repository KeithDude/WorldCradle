"""config.py — persistent dashboard config (secret key + admin password hash).

Stored as JSON in the data root (see paths.py), mode 0600. The admin password
is stored only as a bcrypt hash. On first run the file is created with a fresh
secret key and no admin password (login disabled until one is set via
manage.py).

Writes are serialised and atomic. Changing settings must go through `update()`
so two requests can't overwrite each other's change, and an unreadable config
file is never replaced with defaults — see `load()`.
"""
from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import secrets
import tempfile
import threading

import bcrypt

import paths

paths.ensure_home()
CONFIG_PATH = paths.CONFIG_FILE

DEFAULTS = {
    "secret_key": "",
    "admin_password_hash": "",
    "setup_code": "",              # one-time first-run code (see new_setup_code); cleared on use
    "checklist_hidden": False,     # operator dismissed the getting-started checklist
    "cert_domain": "",             # name on the Let's Encrypt certificate ("" = self-signed)
    "cert_http_port": 8080,        # local port certbot answers on (router: internet 80 → this)
    # Only used by the built-in dev server (`python app.py`). The real service
    # is gunicorn, whose address/port/TLS come from gamedash.service.
    "bind_host": "0.0.0.0",
    "bind_port": 8770,
    "satisfactory_api_token": "",       # optional static Bearer token override; otherwise the
                                        # Satisfactory password comes from the secrets file
    "alert_channel": "none",       # none | discord | ntfy | webhook
    "alert_target": "",            # webhook URL or ntfy topic URL
    "alert_on_recovery": True,
    "alert_on_unreachable": True,
    "alert_on_disabled": False,
    # --- deployment-specific (so this isn't tied to one machine) ----------
    "public_host": "",                       # join address; "" → use the browser's hostname
    "secrets_conf": paths.SECRETS_FILE,      # central password file (the 2 game passwords)
    "backups_dir": "",                       # save-backup root ("" → ~/.local/share/gamedash/backups)
    "ark_cluster_id": "gamedash",            # shared cluster id for ARK maps (transfer between maps)
    "server_name_prefix": "",                # optional prefix prepended to ARK session names
    "port_pool": {},                         # optional {game/query/rcon: [low, high]} ranges
                                             # for NEW instances; empty → use each game
                                             # template's built-in default ports (see ports.py)
    "default_backup_keep": 5,                # default retention for a new server's backups
    "install_dirs": {                        # per-game install dirs (provisioning templates)
        "ark": "~/arkserver",
        "valheim": "~/valheimserver",
        "palworld": "~/palworldserver",
        "satisfactory": "~/satisfactoryserver",
        "abiotic": "~/abioticserver",
        "dst": "~/dstserver",
        "minecraft": "~/minecraftserver",
    },
}


def install_dir(kind: str) -> str:
    """Expanded install dir for a game kind (from config, with a sane default)."""
    import os
    # games added later don't need a DEFAULTS entry: they live in ~/<kind>server
    d = (load().get("install_dirs", {}).get(kind) or DEFAULTS["install_dirs"].get(kind)
         or f"~/{kind}server")
    return os.path.expanduser(d)


def secrets_path() -> str:
    import os
    return os.path.expanduser(load().get("secrets_conf") or paths.SECRETS_FILE)

# Keys that are safe to expose/edit from the admin UI (no secret_key / hash).
ALERT_KEYS = ("alert_channel", "alert_target", "alert_on_recovery",
              "alert_on_unreachable", "alert_on_disabled")


_lock = threading.RLock()
# Used only while the config file is unreadable (see load): sessions signed with
# it die with the process, and it is never written to disk.
_EPHEMERAL_KEY = secrets.token_hex(32)
_warned_unreadable = False


def load() -> dict:
    """Current config (defaults overlaid with the file).

    If the file exists but can't be parsed, it is LEFT ALONE: we return the
    defaults with no admin password (so login is refused — fail closed) and a
    throwaway secret key, and log loudly. Overwriting it here would silently
    throw away the admin password and every setting."""
    global _warned_unreadable
    cfg = dict(DEFAULTS)
    with _lock:
        if os.path.exists(CONFIG_PATH):
            try:
                with open(CONFIG_PATH, encoding="utf-8") as f:
                    data = json.load(f)
                if not isinstance(data, dict):
                    raise ValueError("config root is not an object")
            except (OSError, ValueError) as e:
                if not _warned_unreadable:
                    _warned_unreadable = True
                    logging.getLogger("gamedash").error(
                        "config file %s is unreadable (%s) — NOT overwriting it; login is "
                        "disabled until it is repaired or removed.", CONFIG_PATH, e)
                cfg["secret_key"] = _EPHEMERAL_KEY
                cfg["_unreadable"] = True
                return cfg
            cfg.update(data)
        if not cfg["secret_key"]:
            cfg["secret_key"] = secrets.token_hex(32)
            save(cfg)
    return cfg


def save(cfg: dict) -> None:
    if cfg.get("_unreadable"):
        raise RuntimeError(f"refusing to overwrite unreadable config file {CONFIG_PATH}")
    with _lock:
        # unique temp file in the same dir (created 0600) → atomic replace
        fd, tmp = tempfile.mkstemp(prefix=".config-", suffix=".tmp",
                                   dir=os.path.dirname(CONFIG_PATH))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(cfg, f, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, CONFIG_PATH)
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise


def update(change) -> dict:
    """Atomic read-modify-write: `change(cfg)` mutates the freshly loaded config
    under the lock, then it is saved. Returns the saved config."""
    with _lock:
        cfg = load()
        change(cfg)
        save(cfg)
        return cfg


def auth_version() -> str:
    """Fingerprint of the current admin credentials. Stored in the session at
    login and compared on every request, so changing the admin password (or the
    secret key) signs out every existing session."""
    cfg = load()
    raw = (cfg.get("admin_password_hash", "") + "|" + cfg.get("secret_key", "")).encode()
    return hashlib.sha256(raw).hexdigest()[:24]


_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"   # no 0/O/1/I to misread


def new_setup_code() -> str:
    """Create (and store) the one-time code that lets whoever installed GameDash
    choose the admin password in the browser. 12 characters ≈ 60 bits; guesses
    are also rate-limited by the login lockout."""
    raw = "".join(secrets.choice(_CODE_ALPHABET) for _ in range(12))
    code = "-".join(raw[i:i + 4] for i in range(0, 12, 4))
    update(lambda cfg: cfg.__setitem__("setup_code", code))
    return code


def check_setup_code(code: str) -> bool:
    want = load().get("setup_code", "")
    got = "".join(ch for ch in (code or "").upper() if ch.isalnum())
    return bool(want) and secrets.compare_digest(got, want.replace("-", ""))


def needs_setup() -> bool:
    """True until an admin password exists (and the config is readable)."""
    cfg = load()
    return not cfg.get("_unreadable") and not cfg.get("admin_password_hash")


def _prehash(password: str) -> bytes:
    """SHA-256 then base64 the password before bcrypt. This sidesteps bcrypt's
    72-byte truncation (long passphrases stay distinct) and its NUL-byte
    truncation (base64 output contains no NUL bytes). Result is 44 bytes."""
    digest = hashlib.sha256(password.encode("utf-8")).digest()
    return base64.b64encode(digest)


def set_password(password: str) -> None:
    hashed = bcrypt.hashpw(_prehash(password), bcrypt.gensalt()).decode()

    def change(cfg):
        cfg["admin_password_hash"] = hashed
        cfg.pop("setup_code", None)   # single use: gone as soon as a password exists
    update(change)


def check_password(password: str) -> bool:
    cfg = load()
    h = cfg.get("admin_password_hash", "")
    if not h:
        return False
    try:
        return bcrypt.checkpw(_prehash(password), h.encode())
    except ValueError:
        return False
