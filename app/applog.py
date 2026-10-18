"""applog.py — logging for worldcradle.

Two rotating-file loggers (also echoed to stderr → systemd journal):
  * app_log  (logs/worldcradle.log)  — errors, warnings, debug/operational events.
  * audit_log(logs/audit.log)     — security events: logins, lockouts, every
                                     admin control action, settings changes.

Logs live in <data root>/logs/ (dir 0700, files 0600) — they can contain source
IPs and player names, so they're owner-only.
"""
from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler

import paths

LOG_DIR = paths.LOG_DIR
os.makedirs(LOG_DIR, exist_ok=True)
try:
    os.chmod(LOG_DIR, 0o700)
except OSError:
    pass


def _logger(name: str, filename: str, level: int = logging.INFO) -> logging.Logger:
    lg = logging.getLogger(name)
    lg.setLevel(level)
    lg.propagate = False
    if not lg.handlers:
        path = os.path.join(LOG_DIR, filename)
        fh = RotatingFileHandler(path, maxBytes=2_000_000, backupCount=5)
        fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s",
                                          "%Y-%m-%d %H:%M:%S"))
        lg.addHandler(fh)
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
        if not os.environ.get("WORLDCRADLE_QUIET_LOG"):   # the `worldcradle` command keeps its screen clean
            sh = logging.StreamHandler()  # → stderr → journald (journalctl --user -u worldcradle)
            sh.setFormatter(logging.Formatter("%(name)s %(levelname)s %(message)s"))
            lg.addHandler(sh)
    return lg


app_log = _logger("worldcradle", "worldcradle.log")
audit_log = _logger("worldcradle.audit", "audit.log")
access_log = _logger("worldcradle.access", "access.log")
