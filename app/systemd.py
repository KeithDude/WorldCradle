"""systemd.py — the one way WorldCradle runs `systemctl --user`.

The dashboard and every game server are systemd services of the account WorldCradle runs as, so
starting, stopping and asking about them all goes through here.
"""
from __future__ import annotations

import subprocess

from games.base import ActionError

QUICK = 5      # seconds for a status question
CHANGE = 130   # seconds for start / stop / restart: a game server may take a while to save and stop


def run(*args: str, timeout: float = CHANGE) -> subprocess.CompletedProcess:
    """Run `systemctl --user <args>`. Never raises: a timeout, or systemctl missing, comes back as
    a failed result (returncode -1) with the reason in stderr."""
    try:
        return subprocess.run(["systemctl", "--user", *args], capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(args, -1, "", f"it took longer than {timeout:g} seconds")
    except OSError as e:
        return subprocess.CompletedProcess(args, -1, "", str(e))


def check(*args: str, timeout: float = CHANGE, failed: str = "") -> None:
    """Like run(), but a failure raises ActionError: `failed` (in plain words) and systemd's reason."""
    r = run(*args, timeout=timeout)
    if r.returncode != 0:
        why = (r.stderr or r.stdout).strip() or f"exit status {r.returncode}"
        raise ActionError(f"{failed or 'systemctl ' + ' '.join(args) + ' failed'}: {why}")


def is_active(unit: str) -> bool:
    """Is the service running?"""
    return run("is-active", unit, timeout=QUICK).stdout.strip() == "active"


def is_enabled(unit: str) -> bool:
    """Does the service start by itself when the computer starts?"""
    return run("is-enabled", unit, timeout=QUICK).stdout.strip() == "enabled"


def stop_limit(unit: str) -> float:
    """How long systemd gives the service to stop (its TimeoutStopSec), in seconds — so a start,
    stop or restart can wait for a game that takes minutes to save. CHANGE if unknown."""
    text = show(unit, "TimeoutStopUSec").get("TimeoutStopUSec", "")
    units = {"ms": 0.001, "s": 1, "min": 60, "h": 3600}
    total = 0.0
    for part in text.split():
        num = part.rstrip("abcdefghijklmnopqrstuvwxyz")
        try:
            total += float(num) * units[part[len(num):] or "s"]
        except (ValueError, KeyError):
            return CHANGE                        # "infinity" or something unexpected
    return total or CHANGE


def show(unit: str, *properties: str) -> dict[str, str]:
    """Some of the service's properties, e.g. show(unit, "NRestarts", "SubState")."""
    args = [a for p in properties for a in ("-p", p)]
    out = run("show", unit, *args, timeout=QUICK).stdout
    return dict(line.split("=", 1) for line in out.splitlines() if "=" in line)
