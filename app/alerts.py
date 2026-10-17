"""alerts.py — detect server-state transitions and notify.

The poller calls AlertEngine.process(snapshot) each cycle. We alert on:
  * online -> offline           ("DOWN")
  * offline -> online           ("RECOVERED", optional)
  * running but unreachable for N consecutive polls ("UNREACHABLE", optional)

False-positive avoidance: when the dashboard itself stops/restarts a server it
calls suppress(key, secs); a down inside that window is expected and skipped.
A server that isn't set to start with the computer (the owner stopped it) doesn't alert unless
alert_on_disabled.

Alerts go to every destination set up in Settings → Alerts (the services are in
notifiers.py). Sending is best-effort and never raises into the poller.
"""
from __future__ import annotations

import threading
import time

import config
import notifiers
from applog import app_log

UNREACHABLE_POLLS = 3   # consecutive running-but-unreachable polls before alerting

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

def destinations(cfg: dict | None = None) -> list[dict]:
    """Where alerts go. Settings from before multiple destinations existed (one alert_channel +
    alert_target) count as a single destination."""
    cfg = cfg or config.load()
    dests = [d for d in cfg.get("alert_destinations") or [] if isinstance(d, dict)]
    if not dests and cfg.get("alert_channel", "none") in notifiers.SERVICES and cfg.get("alert_target"):
        dests = [{"type": cfg["alert_channel"], "url": cfg["alert_target"]}]
    return dests


def _send_one(dest: dict, title: str, message: str, level: str) -> dict:
    """Send to one destination. Never raises (the poller calls this): returns
    {"service", "ok", "error"} and logs a failure."""
    label = notifiers.SERVICES.get(dest.get("type"), {}).get("label", dest.get("type"))
    try:
        notifiers.send(dest, title, message, level)
        return {"service": label, "ok": True, "error": ""}
    except notifiers.NotifyError as e:
        app_log.warning("alert delivery to %s failed: %s", label, e)
        return {"service": label, "ok": False, "error": str(e)}
    except Exception as e:   # never let alerting break the poll loop
        app_log.warning("alert delivery to %s failed: %r", label, e)
        return {"service": label, "ok": False, "error": "unexpected error — see the GameDash log"}


def _deliver(title: str, message: str, level: str) -> list[dict]:
    """Send to every destination; what happened for each, as _send_one reports it."""
    return [_send_one(d, title, message, level) for d in destinations()]


def notify(title: str, message: str, level: str = "warn") -> None:
    """Send a one-off notice (not tied to a server state transition) through the
    configured destinations. Best-effort; a no-op when none are set up."""
    _deliver(title, message, level)


def send_test(dest: dict | None = None) -> list[dict]:
    """Send a test alert to one destination, or to all of them. Returns what happened for each
    ([] when there is nowhere to send to) — the Settings page shows it."""
    title, message = "🎮 GameDash test alert", "If you can read this, GameDash alerts reach you here."
    if dest is None:
        return _deliver(title, message, "good")
    return [_send_one(dest, title, message, "good")]


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
                if not _is_suppressed(key) and (v.get("enabled") or on_disabled):
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
