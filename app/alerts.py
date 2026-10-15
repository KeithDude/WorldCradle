"""alerts.py — detect server-state transitions and notify.

The poller calls AlertEngine.process(snapshot) each cycle. We alert on:
  * online -> offline           ("DOWN")
  * offline -> online           ("RECOVERED", optional)
  * running but unreachable for N consecutive polls ("UNREACHABLE", optional)

False-positive avoidance: when the dashboard itself stops/restarts a server it
calls suppress(key, secs); a down inside that window is expected and skipped.
Disabled (intentionally parked) servers don't alert unless alert_on_disabled.

Delivery is pluggable via config: discord webhook, ntfy topic, generic webhook,
or none. All sends are best-effort and never raise into the poller.
"""
from __future__ import annotations

import threading
import time

import requests

import config
from applog import app_log

UNREACHABLE_POLLS = 3   # consecutive running-but-unreachable polls before alerting
SEND_TIMEOUT = 6.0

# ---- suppression (set by controls.py on dashboard-initiated stop/restart) ----
_suppress: dict[str, float] = {}
_lock = threading.Lock()


def suppress(key: str, seconds: float) -> None:
    with _lock:
        _suppress[key] = time.time() + seconds


def _is_suppressed(key: str) -> bool:
    with _lock:
        exp = _suppress.get(key, 0)
        if exp and time.time() < exp:
            return True
        _suppress.pop(key, None)
        return False


# ---- delivery --------------------------------------------------------------

def _deliver(title: str, message: str, level: str) -> None:
    cfg = config.load()
    channel = cfg.get("alert_channel", "none")
    target = cfg.get("alert_target", "")
    if channel == "none" or not target:
        return
    text = f"{title}\n{message}"
    try:
        if channel == "discord":
            # JSON body is UTF-8 — emoji in the title are fine here.
            requests.post(target, json={"content": text[:1900]}, timeout=SEND_TIMEOUT)
        elif channel == "ntfy":
            # ntfy's Title is an HTTP header → must be ASCII. Keep the emoji as a
            # ntfy Tag (rendered client-side) and strip it from the header.
            tag = {"bad": "rotating_light", "good": "white_check_mark",
                   "warn": "warning"}.get(level, "video_game")
            prio = {"bad": "high", "good": "default", "warn": "high"}.get(level, "default")
            ascii_title = title.encode("ascii", "ignore").decode().strip() or "gamedash"
            requests.post(target, data=message.encode("utf-8"),
                          headers={"Title": ascii_title, "Priority": prio, "Tags": tag},
                          timeout=SEND_TIMEOUT)
        elif channel == "webhook":
            requests.post(target, json={"title": title, "message": message,
                                        "level": level}, timeout=SEND_TIMEOUT)
    except Exception as e:  # never let alerting break the poll loop, but log it
        app_log.warning("alert delivery to %s failed: %r", channel, e)


def notify(title: str, message: str, level: str = "warn") -> None:
    """Send a one-off notice (not tied to a server state transition) through the
    configured channel. Best-effort; a no-op when no channel is set up."""
    _deliver(title, message, level)


def send_test() -> bool:
    """Send a test alert; returns False if no channel is configured."""
    cfg = config.load()
    if cfg.get("alert_channel", "none") == "none" or not cfg.get("alert_target"):
        return False
    _deliver("🎮 gamedash test alert",
             "If you can read this, alert delivery is working.", "good")
    return True


# ---- engine ----------------------------------------------------------------

class AlertEngine:
    def __init__(self):
        # per-key: {"online": bool|None, "unreach_count": int, "unreach_alerted": bool}
        self._state: dict[str, dict] = {}

    def process(self, snapshot: dict) -> None:
        cfg = config.load()
        on_recovery = cfg.get("alert_on_recovery", True)
        on_unreachable = cfg.get("alert_on_unreachable", True)
        on_disabled = cfg.get("alert_on_disabled", False)

        for v in snapshot.get("servers", {}).values():
            key = v["key"]
            prev = self._state.get(key)
            online = bool(v["online"])
            st = prev or {"online": None, "unreach_count": 0, "unreach_alerted": False}

            # online -> offline
            if prev is not None and prev["online"] and not online:
                parked = v.get("slot_group") and v.get("note")
                if not _is_suppressed(key) and not parked and (v.get("enabled") or on_disabled):
                    _deliver(f"🔴 {v['name']} is DOWN",
                             f"{v['name']} went offline at {_now()}.", "bad")

            # offline -> online
            if prev is not None and prev["online"] is False and online and on_recovery:
                if not _is_suppressed(key):
                    _deliver(f"🟢 {v['name']} recovered",
                             f"{v['name']} is back online at {_now()}.", "good")

            # running but unreachable for N consecutive polls
            if online and v.get("reachable") is False:
                st["unreach_count"] = st.get("unreach_count", 0) + 1
                if (on_unreachable and st["unreach_count"] >= UNREACHABLE_POLLS
                        and not st.get("unreach_alerted") and not _is_suppressed(key)):
                    _deliver(f"🟠 {v['name']} unreachable",
                             f"{v['name']} is running but not answering on its "
                             f"public port (possible hang) as of {_now()}.", "warn")
                    st["unreach_alerted"] = True
            else:
                st["unreach_count"] = 0
                st["unreach_alerted"] = False

            st["online"] = online
            self._state[key] = st


def _now() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")
