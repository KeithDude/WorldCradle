"""updates.py — periodic Steam build-update checker for the game servers.

steamcmd is slow (~10-30s/app), so this runs on its own thread on a long
interval (default 6h) and caches results; the dashboard reads the cache. An
admin "Check now" can trigger an immediate refresh. Each game's installed
build id is compared to the latest public one; steam.py reads both.
"""
from __future__ import annotations

import threading
import time

import steam
from applog import app_log
from registry import load_servers

CHECK_INTERVAL = 6 * 3600  # seconds between automatic checks
FIRST_CHECK_DELAY = 45     # let the app settle before the first (slow) check


def _games() -> list[dict]:
    """Unique (app, install_dir, game-name) from the registry — ARK's maps
    share one install, so dedupe by app id."""
    seen: dict[int, dict] = {}
    for s in load_servers():
        if s.steam_app and s.steam_app not in seen:
            seen[s.steam_app] = {"app": s.steam_app, "dir": s.install_dir,
                                 "game": s.name.split(" · ", 1)[0]}
    return list(seen.values())


class UpdateChecker:
    def __init__(self, interval: int = CHECK_INTERVAL):
        self.interval = interval
        self._lock = threading.Lock()
        self._refresh_lock = threading.Lock()
        self._data: dict[int, dict] = {}
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._wake = threading.Event()

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._loop, name="updates", daemon=True)
        self._thread.start()

    def trigger(self):
        """Ask the background thread to refresh now (non-blocking)."""
        self._wake.set()

    def snapshot(self) -> dict:
        with self._lock:
            return dict(self._data)

    def _loop(self):
        self._stop.wait(FIRST_CHECK_DELAY)
        while not self._stop.is_set():
            self.refresh()
            self._wake.wait(self.interval)
            self._wake.clear()

    def refresh(self):
        if not self._refresh_lock.acquire(blocking=False):
            return  # one already running
        try:
            for g in _games():
                installed = steam.installed_build(g["dir"], g["app"])
                latest = steam.latest_build(g["app"])
                rec = {
                    "game": g["game"], "app": g["app"],
                    "installed": installed, "latest": latest,
                    "up_to_date": installed is not None and installed == latest,
                    "ok": latest is not None,
                    "checked_ts": time.time(),
                }
                with self._lock:
                    self._data[g["app"]] = rec
        except Exception:   # never let the checker thread die
            app_log.exception("update check failed")
        finally:
            self._refresh_lock.release()


checker = UpdateChecker()
